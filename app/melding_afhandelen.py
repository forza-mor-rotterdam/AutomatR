from listeners import MeldingAfhandelen

rule_sets = (
    {
        "key": "taak_aantal_1_en_signalen_anoniem",
        "title": "Melding met 1 taak, waarbij alle signalen anoniem gemeld zijn",
        "active": False,
        "required_vars": [],
        "rules": (
            ("Heeft de melding de status 'Controle'", "status&['naam'] == 'controle'"),
            (
                "Is er maar één taakopdracht succesvol afgehandeld zonder intere opmerking",
                "[taakopdracht for taakopdracht in taakopdrachten_voor_melding if not taakopdracht&['verwijderd_op']].length == 1 and [taakopdracht for taakopdracht in taakopdrachten_voor_melding if not taakopdracht&['verwijderd_op'] and taakopdracht&['afgesloten_op'] and taakopdracht&['resolutie'] == 'opgelost' and taakopdracht&['taakgebeurtenissen_voor_taakopdracht'] and [taakgebeurtenis for taakgebeurtenis in taakopdracht['taakgebeurtenissen_voor_taakopdracht'] if taakgebeurtenis&['resolutie'] == 'opgelost' and (not taakgebeurtenis&['omschrijving_intern'])]].length == 1",
            ),
            (
                "Hebben alle melders, de melding annoniem gemeld",
                "not [signaal for signaal in signalen_voor_melding if signaal&['melder'] and [value for value in signaal['melder'].values if value and value.to_str.as_lower != 'anoniem']]",
            ),
        ),
        "data": {
            "omschrijving_intern": "",
            "omschrijving_extern": "Afgehandeld door bot",
        },
    },
    {
        "key": "taak_aantal_1_met_specifiek_taaktype_en_signalen_anoniem",
        "title": "Melding met 1 taak voor Havenbedrijf Rotterdam, waarbij alle signalen anoniem gemeld zijn",
        "active": True,
        "required_vars": {
            "taakapplicatie_taaktype_url": "default",
            "omschrijving_extern": "default",
        },
        "rules": (
            ("Heeft de melding de status 'Controle'?", "status&['naam'] == 'controle'"),
            (
                "Is er maar één taakopdracht succesvol afgehandeld zonder intere opmerking met als taaktype '{taakapplicatie_taaktype_url}'?",
                "[taakopdracht for taakopdracht in taakopdrachten_voor_melding if not taakopdracht&['verwijderd_op']].length == 1 and [taakopdracht for taakopdracht in taakopdrachten_voor_melding if not taakopdracht&['verwijderd_op'] and taakopdracht&['afgesloten_op'] and taakopdracht&['resolutie'] == 'opgelost' and taakopdracht&['taaktype'] == '{taakapplicatie_taaktype_url}' and taakopdracht&['taakgebeurtenissen_voor_taakopdracht'] and [taakgebeurtenis for taakgebeurtenis in taakopdracht['taakgebeurtenissen_voor_taakopdracht'] if taakgebeurtenis&['resolutie'] == 'opgelost' and (not taakgebeurtenis&['omschrijving_intern'])]].length == 1",
            ),
            (
                "Hebben alle melders, de melding annoniem gemeld?",
                "not [signaal for signaal in signalen_voor_melding if signaal&['melder'] and [value for value in signaal['melder'].values if value and value.to_str.as_lower != 'anoniem']]",
            ),
        ),
        "data": {
            "omschrijving_intern": "",
            "omschrijving_extern": "{omschrijving_extern}",
        },
    },
)

MeldingAfhandelen(
    routing_key="melding.*.taakopdrachten_veranderd",
    rule_sets=rule_sets,
).start()
