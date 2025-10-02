import json
import logging
import os
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


class Listener(threading.Thread):
    routing_key = None

    def __init__(self):
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
        # self.test(json.loads(body))

    def test(self, bericht):
        raise NotImplementedError()


class MeldingAfhandelen(Listener):
    routing_key = "melding.*.taakopdrachten_veranderd"

    def test(self, bericht):
        logger.info(json.dumps(bericht, indent=4))
        melding_url = bericht.get("_links", {}).get("melding", {}).get("href")
        melding_data = self.mor_core_service.haal_data(melding_url, raw_response=False)

        logger.info("Start test")
        rules = (
            ("Heeft de melding de status 'Controle'", "status&['naam'] == 'controle'"),
            (
                "Is er maar één taakopdracht succesvol afgehandeld zonder intere opmerking",
                "[taakopdracht for taakopdracht in taakopdrachten_voor_melding if not taakopdracht&['verwijderd_op']].length == 1 and [taakopdracht for taakopdracht in taakopdrachten_voor_melding if not taakopdracht&['verwijderd_op'] and taakopdracht&['afgesloten_op'] and taakopdracht&['resolutie'] == 'opgelost' and taakopdracht&['taakgebeurtenissen_voor_taakopdracht'] and [taakgebeurtenis for taakgebeurtenis in taakopdracht['taakgebeurtenissen_voor_taakopdracht'] if taakgebeurtenis&['resolutie'] == 'opgelost' and (not taakgebeurtenis&['omschrijving_intern'])]].length == 1",
            ),
            (
                "Hebben alle melders, de melding annoniem gemeld",
                "not [signaal for signaal in signalen_voor_melding if signaal&['melder'] and [value for value in signaal['melder'].values if value and value.to_str.as_lower != 'anoniem']]",
            ),
        )

        test_results = [[r[0], R(r[1]).matches(melding_data)] for r in rules]
        test_results_passed = not bool([t[0] for t in test_results if not t[1]])

        test_results_verbose = [
            f'{test[0]}? {"Ja" if test[1] else "Nee"}' for test in test_results
        ]
        omschrijving_intern = f"Melding afhandelen? {'Ja' if test_results_passed else 'Nee'}, {', '.join(test_results_verbose)}"

        logger.info(f"Melding afhandelen? {'Ja' if test_results_passed else 'Nee'}")
        for test_result_verbose in test_results_verbose:
            logger.info(test_result_verbose)

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
            logger.info(
                f"Melding afhandelen met data: {json.dumps(afhandel_data, indent=4)}"
            )
            melding_afhandelen_response = self.mor_core_service.melding_afhandelen_v2(
                **afhandel_data
            )

            if melding_afhandelen_response.get("error"):
                logger.error(
                    f"Melding '{melding_url}', is niet afgehandeld, error: {melding_afhandelen_response.get('error')}"
                )
            else:
                logger.info(f"Melding '{melding_url}', is afgehandeld")

        elif not ENVIRONMENT_IS_PRODUCTION:
            self.mor_core_service.melding_gebeurtenis_toevoegen(
                melding_data.get("uuid"),
                omschrijving_intern=omschrijving_intern,
                gebruiker=BOT_USER_EMAIL,
            )
