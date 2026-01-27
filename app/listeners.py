import json
import logging
import os
import re
import threading
from logging import config

import pika
import requests
from rule_engine import Rule as R
from services import MORCoreService, TaakRService

config.fileConfig("logging.conf", disable_existing_loggers=False)

logger = logging.getLogger(__name__)

ENVIRONMENT_DEVELOPMENT = "development"
ENVIRONMENT_TEST = "test"
ENVIRONMENT_ACCEPTANCE = "acceptance"
ENVIRONMENT_PRODUCTION = "production"

ENVIRONMENT = os.getenv("ENVIRONMENT")
BOT_USER_EMAIL = os.getenv("BOT_USER_EMAIL", "botjeknor@rotterdam.nl")

GIT_SHA = os.getenv("GIT_SHA", "Not found")


class Listener(threading.Thread):
    routing_key = None
    rule_sets = []
    planr_url = ""
    settings_url = ""

    def __init__(self, routing_key, rule_sets):
        self.routing_key = routing_key
        self.rule_sets = rule_sets
        self.planr_url = os.getenv("PLANR_URL", "https://planr-test.forzamor.nl")
        self.settings_url = f'{self.planr_url.strip("/")}/api/v1/automatr-settings/'

        threading.Thread.__init__(self)
        prefetch_count = int(os.getenv("RABBITMQ_PREFETCH_COUNT", 1))

        connection = pika.BlockingConnection(
            pika.connection.URLParameters(os.getenv("RABBITMQ_URL"))
        )
        self.channel = connection.channel()
        result = self.channel.queue_declare(queue="", exclusive=True)
        queue_name = result.method.queue
        self.channel.queue_bind(
            queue=queue_name,
            exchange=os.getenv("RABBITMQ_EXCHANGE"),
            routing_key=self.routing_key,
        )
        self.channel.basic_qos(prefetch_count=prefetch_count)
        self.channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
        self.mor_core_service = MORCoreService()

    def run(self):
        logger.info(f"GIT_SHA: {GIT_SHA}")
        logger.info(
            f"Joblisterner={self.__class__.__name__}, with routing_key={self.routing_key}"
        )
        self.channel.start_consuming()

    def callback(self, channel, method, properties, body):
        logger.debug(f"channel: {channel}")
        logger.debug(f"method: {method}")
        logger.debug(f"properties: {properties}")
        logger.debug(f"body: {body}")

        channel.basic_ack(delivery_tag=method.delivery_tag)
        self.test(json.loads(body))

    def _camel_case_string(self, string):
        return re.sub(r"([a-z])([A-Z])", r"\1_\2", string).lower()

    def get_settings(self):
        response = requests.get(url=self.settings_url)
        response.raise_for_status()
        try:
            return response.json()
        except Exception as e:
            return print(e)

    def test(self, bericht):
        raise NotImplementedError()


class MeldingAfhandelen(Listener):
    def test(self, bericht):
        logger.info(json.dumps(bericht, indent=4))
        melding_url = bericht.get("_links", {}).get("melding", {}).get("href")
        melding_data = self.mor_core_service.haal_data(melding_url, raw_response=False)

        settings_key = "melding_afhandelen_door_taak"

        all_settings = self.get_settings()

        logger.info(f"MeldingAfhandelen melding_url: {melding_url}")
        logger.info(f"MeldingAfhandelen in omgeving: {ENVIRONMENT}")
        logger.info(
            f'MeldingAfhandelen all variables: {all_settings.get("results", [])}'
        )

        logger.info("Start MeldingAfhandelen tests")

        rule_set = self.rule_sets.get(settings_key, {})
        rules = rule_set.get("rules", [])
        logger.info(f"Rule key: {rule_set['key']}")
        rule_variables = next(
            iter(
                [
                    setting.get("settings", []) if setting.get("settings") else []
                    for setting in all_settings.get("results", [])
                    if setting["name"] == settings_key
                ]
            ),
            [],
        )

        logger.info(
            f"Aantal variabelen varianten voor deze rule: {len(rule_variables)}"
        )
        for vars in rule_variables:
            required_vars = (
                "taakapplicatie_taaktype_url",
                "omschrijving_extern",
            )
            if len([k for k, v in vars.items() if k in required_vars and v]) < len(
                required_vars
            ):
                logger.warning(
                    "Settings variabele(n) ontbreken: 'taakapplicatie_taaktype_url' en 'omschrijving_extern' zijn verplicht"
                )
                continue
            vars = {k: vars.get(k, v) for k, v in rule_set.get("input", {}).items()}
            logger.info(f"Start test for rule set with variables: {vars}")
            test_results = [
                [r[0].format(**vars), R(r[1].format(**vars)).matches(melding_data)]
                for r in rules
            ]
            test_results_passed = not bool([t[0] for t in test_results if not t[1]])

            test_results_verbose = [
                f'{test[0]} {"Ja" if test[1] else "Nee"}' for test in test_results
            ]
            omschrijving_intern = f"Melding afhandelen? {'Ja' if test_results_passed else 'Nee'}, {', '.join(test_results_verbose)}"

            logger.info(f"Melding afhandelen? {'Ja' if test_results_passed else 'Nee'}")
            logger.info(f"Melding tests? {omschrijving_intern}")
            for test_result_verbose in test_results_verbose:
                logger.info(test_result_verbose)

            if test_results_passed:
                default_afhandel_data = {
                    "uuid": melding_data.get("uuid"),
                    "resolutie": "opgelost",
                    "gebruiker": BOT_USER_EMAIL,
                }
                afhandel_data = {
                    k: v.format(**vars)
                    for k, v in rule_set.get("data", {}).items()
                    if v.format(**vars)
                }
                default_afhandel_data.update(afhandel_data)

                logger.info(
                    f"Melding afhandelen met data: {json.dumps(default_afhandel_data, indent=4)}"
                )
                if not default_afhandel_data.get("omschrijving_extern"):
                    logger.warning("Melding afhandelen omschrijving_extern ontbreekt")
                    break

                melding_afhandelen_response = (
                    self.mor_core_service.melding_afhandelen_v2(**default_afhandel_data)
                )

                if melding_afhandelen_response.get("error"):
                    logger.error(
                        f"Melding '{melding_url}', is niet afgehandeld, error: {melding_afhandelen_response.get('error')}"
                    )
                else:
                    logger.info(f"Melding '{melding_url}', is afgehandeld")

                break


class TakenAanmaken(Listener):
    def test(self, bericht):
        logger.info(json.dumps(bericht, indent=4))
        melding_url = bericht.get("_links", {}).get("melding", {}).get("href")
        melding_data = self.mor_core_service.haal_data(melding_url, raw_response=False)

        settings_key = "taak_aanmaken_bij_onderwerp"

        all_settings = all_settings = self.get_settings()

        logger.info(f"TakenAanmaken melding_url: {melding_url}")
        logger.info(f'TakenAanmaken all variables: {all_settings.get("results", [])}')

        logger.info("Start TakenAanmaken tests")

        rule_set = self.rule_sets.get(settings_key, {})
        rules = rule_set.get("rules", [])
        logger.info(f"Rules aantal: {len(rules)}")
        rule_variables = next(
            iter(
                [
                    setting.get("settings", []) if setting.get("settings") else []
                    for setting in all_settings.get("results", [])
                    if setting["name"] == settings_key
                ]
            ),
            [],
        )

        logger.info(
            f"Aantal variabelen varianten voor deze rule: {len(rule_variables)}"
        )
        for rule_variable_set in rule_variables:
            rule_test_variables = [
                {
                    "onderwerp_url": rule_variable_set.get("onderwerp", {}).get("url"),
                    "question": question.get("question"),
                    "answer": answer,
                    "answers_count": len(question.get("answers", [])),
                }
                for question in rule_variable_set.get("onderwerp", {}).get(
                    "questions", []
                )
                if rule_variable_set.get("onderwerp", {}).get("url")
                for answer in question.get("answers", [])
            ]
            all_tests = []
            all_results_verbose = []
            for vars in rule_test_variables:
                logger.info(f"Start test for rule set with variables: {vars}")
                test_results = [
                    [
                        r[0].format(**vars),
                        R(r[1].format(**vars)).matches(melding_data),
                    ]
                    for r in rules
                ]
                test_results_passed = all([t[1] for t in test_results])

                all_tests.append(test_results_passed)

                test_results_verbose = [
                    f'{test[0]} {"Ja" if test[1] else "Nee"}' for test in test_results
                ]
                all_results_verbose = all_results_verbose + test_results_verbose

            omschrijving_intern = ", ".join(sorted(list(set(all_results_verbose))))
            logger.info(f"TakenAanmaken: Melding tests? {omschrijving_intern}")

            if rule_test_variables and all(all_tests):
                logger.info(
                    f'Taakopdrachten aantal: {len(rule_variable_set.get("taakopdrachten", []))}'
                )
                for taakopdracht in rule_variable_set.get("taakopdrachten", []):
                    taakapplicatie_taaktype_url = taakopdracht.get("taaktype")
                    logger.info(
                        f"taakapplicatie_taaktype_url: {taakapplicatie_taaktype_url}"
                    )
                    taaktypes_response = TaakRService().get_taaktypes(
                        params={
                            "taakapplicatie_taaktype_url": taakapplicatie_taaktype_url
                        }
                    )
                    if isinstance(taaktypes_response, dict) and taaktypes_response.get(
                        "errors"
                    ):
                        logger.error(
                            f'taaktype response errors: {taaktypes_response.get("errors")}'
                        )
                        continue
                    if taaktypes_response:
                        logger.info(f"taaktypes_response: {taaktypes_response}")
                        taakopdracht_data = {
                            "melding_uuid": melding_data.get("uuid"),
                            "taakapplicatie_taaktype_url": taakapplicatie_taaktype_url,
                            "titel": taaktypes_response[0].get("omschrijving"),
                            "bericht": taakopdracht.get("bericht"),
                            "gebruiker": BOT_USER_EMAIL,
                            "afhankelijkheid": [],
                        }
                        taak_aanmaken_response = self.mor_core_service.taak_aanmaken(
                            **taakopdracht_data
                        )
                        logger.info(f"taak_aanmaken_response: {taak_aanmaken_response}")
                        if taak_aanmaken_response.get("errors"):
                            logger.error(
                                f'taak aanmaken response errors: {taak_aanmaken_response.get("errors")}'
                            )
                            continue
                    else:
                        logger.error(
                            f"het taaktype is niet gevonden: {taakapplicatie_taaktype_url}"
                        )
