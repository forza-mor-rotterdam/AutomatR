import json
import logging
import os
import re
import threading
from logging import config

import pika
from rule_engine import Rule as R
from services import MORCoreService

config.fileConfig("logging.conf", disable_existing_loggers=False)

logger = logging.getLogger(__name__)

ENVIRONMENT_DEVELOPMENT = "development"
ENVIRONMENT_TEST = "test"
ENVIRONMENT_ACCEPTANCE = "acceptance"
ENVIRONMENT_PRODUCTION = "production"

ENVIRONMENT_IS_PRODUCTION = (
    os.getenv("ENVIRONMENT", ENVIRONMENT_PRODUCTION) == ENVIRONMENT_PRODUCTION
)
BOT_USER_EMAIL = os.getenv("BOT_USER_EMAIL", "botjeknor@rotterdam.nl")

GIT_SHA = os.getenv("GIT_SHA", "Not found")


class Listener(threading.Thread):
    routing_key = None
    rule_sets = []

    def __init__(self, routing_key, rule_sets):
        self.routing_key = routing_key
        self.rule_sets = rule_sets

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

    def get_variables(self):
        listener_vars = os.getenv(
            f"LISTENER_{self._camel_case_string(self.__class__.__name__).upper()}",
            "this must generate json error",
        )
        try:
            return json.loads(listener_vars)
        except Exception:
            return {}

    def test(self, bericht):
        raise NotImplementedError()


class MeldingAfhandelen(Listener):
    def test(self, bericht):
        logger.info(json.dumps(bericht, indent=4))
        melding_url = bericht.get("_links", {}).get("melding", {}).get("href")
        melding_data = self.mor_core_service.haal_data(melding_url, raw_response=False)

        variables = self.get_variables()
        logger.info(f"MeldingAfhandelen melding_url: {melding_url}")
        logger.info(f"MeldingAfhandelen all variables: {variables}")

        logger.info("Start MeldingAfhandelen tests")

        active_rule_sets = [
            rule_set for rule_set in self.rule_sets if rule_set.get("active")
        ]
        logger.info(f"Using {len(active_rule_sets)} of {len(self.rule_sets)} rule sets")
        for rule_set in active_rule_sets:
            rules = rule_set.get("rules", [])
            logger.info(f"Rule key: {rule_set['key']}")
            rule_variables = variables.get(rule_set["key"], {})

            if isinstance(rule_variables, dict):
                rule_variables = [rule_variables]
            logger.info(
                f"Aantal variabelen varianten voor deze rule: {len(rule_variables)}"
            )
            for vars in rule_variables:
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

                logger.info(
                    f"Melding afhandelen? {'Ja' if test_results_passed else 'Nee'}"
                )
                for test_result_verbose in test_results_verbose:
                    logger.info(test_result_verbose)

                if not ENVIRONMENT_IS_PRODUCTION:
                    self.mor_core_service.melding_gebeurtenis_toevoegen(
                        melding_data.get("uuid"),
                        omschrijving_intern=omschrijving_intern,
                        gebruiker=BOT_USER_EMAIL,
                    )

                if test_results_passed:
                    afhandel_data = {
                        "uuid": melding_data.get("uuid"),
                        "resolutie": "opgelost",
                        "omschrijving_intern": omschrijving_intern
                        if not ENVIRONMENT_IS_PRODUCTION
                        else "",
                        "omschrijving_extern": "Afgehandeld door bot",
                        "gebruiker": BOT_USER_EMAIL,
                    }
                    afhandel_data.update(
                        {
                            k: v.format(**vars)
                            for k, v in rule_set.get("data", {}).items()
                        }
                    )
                    logger.info(
                        f"Melding afhandelen met data: {json.dumps(afhandel_data, indent=4)}"
                    )
                    melding_afhandelen_response = (
                        self.mor_core_service.melding_afhandelen_v2(**afhandel_data)
                    )

                    if melding_afhandelen_response.get("error"):
                        logger.error(
                            f"Melding '{melding_url}', is niet afgehandeld, error: {melding_afhandelen_response.get('error')}"
                        )
                    else:
                        logger.info(f"Melding '{melding_url}', is afgehandeld")

                    break
