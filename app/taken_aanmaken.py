from listeners import TakenAanmaken

rule_sets = (
    {
        "key": "melding_aangemaakt_met_onderwerp_en_vragen",
        "title": "Melding met specifiek onderwerp en eventueel antwoord op diverse vragen",
        "active": True,
        "required_vars": {
            "taaktype": "default",
            "bericht": "default",
        },
        "rules": (
            (
                "Heeft de melding de status 'Openstaand'?",
                "status&['naam'] == 'openstaand'",
            ),
            (
                "Is de melding gemeld met onderwerp url '{onderwerp_url}'?",
                "onderwerp == '{onderwerp_url}'",
            ),
            (
                "Heeft de melding heeft 1 meldinggebeurtenis?",
                "meldinggebeurtenissen.length == 1",
            ),
            (
                "Is het aantal antwoorden bij de vraag '{question}' {answers_count}?",
                "[signaal for signaal in signalen_voor_melding if signaal&['aanvullende_vragen'] and [vraag for vraag in signaal&['aanvullende_vragen'] if vraag&['question'] == '{question}' and vraag&['answers'].length == {answers_count}]]",
            ),
            (
                "Is de vraag '{question}' bij het onderwerp beantwoord met het volgende antwoord '{answer}'?",
                "[signaal for signaal in signalen_voor_melding if signaal&['aanvullende_vragen'] and [vraag for vraag in signaal&['aanvullende_vragen'] if vraag&['question'] == '{question}' and '{answer}' in vraag&['answers']]]",
            ),
        ),
        "data": {
            "taaktype": "{taaktype}",
            "bericht": "{bericht}",
        },
    },
)

TakenAanmaken(
    routing_key="melding.*.aangemaakt",
    rule_sets=rule_sets,
).start()
