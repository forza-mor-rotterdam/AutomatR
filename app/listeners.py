import json
import logging
import os
import threading

import pika
from services import MORCoreService

logger = logging.getLogger(__name__)


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
        self.test(json.loads(body))

    def test(self, bericht):
        raise NotImplementedError()


class MeldingAfhandelen(Listener):
    routing_key = "melding.*.taakopdrachten_veranderd"

    def test(self, bericht):
        logger.info(json.dumps(bericht, indent=4))
        melding_url = bericht.get("_links", {}).get("melding", {}).get("href")
        melding_data = self.mor_core_service.haal_data(melding_url, raw_response=False)

        logger.info("Start test")

        # test: melding status controle
        if melding_data.get("status", {}).get("naam") != "controle":
            logger.info("Niet afhandelen: De melding heeft niet de status 'Controle'")
            return False

        # test: signalen met anonieme melders
        def signaal_is_anoniem_gemeld(signaal):
            values = [
                v.lower() if isinstance(v, str) else v
                for v in list(signaal.get("melder", {}).values())
            ]
            return not [v for v in values if v and v != "anoniem"]

        signalen = [
            signaal
            for signaal in melding_data.get("signalen_voor_melding", [])
            if not signaal_is_anoniem_gemeld(signaal)
        ]
        if signalen:
            logger.info(
                "Niet afhandelen: Eén of meer signalen bevat niet anonieme info"
            )
            return False

        # test: aantal taken
        taakopdrachten = [
            taakopdracht
            for taakopdracht in melding_data.get("taakopdrachten_voor_melding", [])
            if not taakopdracht.get("verwijderd_op")
        ]
        if len(taakopdrachten) > 1:
            logger.info(
                "Niet afhandelen: Er zijn meerdere taken aangemaakt voor deze melding"
            )
            return False

        if len(taakopdrachten) == 0:
            logger.info(
                "Niet afhandelen: Er zijn geen taken aangemaakt voor deze melding"
            )
            return False

        taakopdracht = taakopdrachten[0]

        # test: taakopdracht afgehandeld
        if not taakopdracht.get("resolutie") and not taakopdracht.get("afgesloten_op"):
            logger.info(
                "Niet afhandelen: De enige valide taakopdracht is niet afgehandeld"
            )
            return False

        # test: taakopdracht afgehandeld met resolutie opgelost
        if (
            taakopdracht.get("resolutie")
            and taakopdracht.get("resolutie") != "opgelost"
            and taakopdracht.get("afgesloten_op")
        ):
            logger.info(
                "Niet afhandelen: De enige valide taakopdracht is niet afgehandeld met resolutie 'opgelost'"
            )
            return False

        # test: taakopdracht afgehandeld met resolutie opgelost zonder omschrijving_intern
        taakgebeurtenissen = [
            taakgebeurtenis
            for taakgebeurtenis in taakopdrachten[0].get(
                "taakgebeurtenissen_voor_taakopdracht", []
            )
            if taakgebeurtenis.get("resolutie")
        ]
        if not taakgebeurtenissen or taakgebeurtenissen[0].get(
            "omschrijving_intern", ""
        ):
            logger.info(
                "Niet afhandelen: De enige valide taakopdracht is afgehandeld met een omschrijving_intern die niet leeg is"
            )

        # afhandelen
        afhandel_data = {
            "uuid": melding_data.get("uuid"),
            "resolutie": "opgelost",
            "omschrijving_intern": "Afgehandeld door bot",
            "omschrijving_extern": "Afgehandeld door bot",
            "gebruiker": os.getenv("BOT_USER_EMAIL", "botjeknor@rotterdam.nl"),
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
