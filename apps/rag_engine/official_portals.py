"""
Registre Officiel des 30 Portals et Sites du Gouvernement de la RDC.
Fournit la source de vérité absolue pour l'orientation citoyenne, le répertoire
et le filtrage strict des recherches gouvernementales (FRD v1.1 - Zero Hallucination).
"""

from typing import List, Dict, Any, Optional

OFFICIAL_DRC_PORTALS: List[Dict[str, Any]] = [
    # 1. Institutions Constitutionnelles & Pouvoir Exécutif
    {
        "id": "presidence",
        "name": "Présidence de la RDC",
        "category": "Institutions Constitutionnelles & Pouvoir Exécutif",
        "url": "http://presidentrdc.cd/",
        "domain": "presidentrdc.cd",
        "description": "Portail officiel du Chef de l'État : ordonnances et décrets présidentiels, discours à la Nation, annonces institutionnelles et communication du Président de la République.",
        "keywords": ["présidence", "président", "chef de l'etat", "ordonnance", "décret présidentiel", "discours", "palais de la nation", "tshisekedi"]
    },
    {
        "id": "primature",
        "name": "Primature de la RDC",
        "category": "Institutions Constitutionnelles & Pouvoir Exécutif",
        "url": "https://www.primature.gouv.cd/",
        "domain": "primature.gouv.cd",
        "description": "Portail officiel du Premier Ministre et du gouvernement central : politiques exécutives, conseils des ministres, arrêtés primatoriaux et coordination de l'action gouvernementale.",
        "keywords": ["primature", "premier ministre", "gouvernement", "conseil des ministres", "décret", "politique générale", "cabinet"]
    },
    {
        "id": "assemblee-nationale",
        "name": "Assemblée Nationale",
        "category": "Institutions Constitutionnelles & Pouvoir Exécutif",
        "url": "https://assemblee-nationale.cd",
        "domain": "assemblee-nationale.cd",
        "description": "Chambre basse du Parlement congolais : ordres du jour législatifs, députés nationaux, propositions et textes de lois votées, contrôle parlementaire.",
        "keywords": ["assemblée nationale", "parlement", "député", "lois votées", "palais du peuple", "législatif", "session parlementaire"]
    },
    {
        "id": "senat",
        "name": "Sénat de la RDC",
        "category": "Institutions Constitutionnelles & Pouvoir Exécutif",
        "url": "https://senat.cd",
        "domain": "senat.cd",
        "description": "Chambre haute du Parlement de la RDC : contrôle parlementaire, révisions constitutionnelles, représentation des provinces et textes législatifs.",
        "keywords": ["sénat", "sénateur", "chambre haute", "parlement", "provinces", "constitution", "législation"]
    },
    {
        "id": "journal-officiel",
        "name": "Journal Officiel de la République Démocratique du Congo",
        "category": "Institutions Constitutionnelles & Pouvoir Exécutif",
        "url": "https://journalofficiel.cd",
        "domain": "journalofficiel.cd",
        "description": "Dépôt légal officiel où sont promulgués et publiés tous les textes de lois, décrets, ordonnances présidentielles et immatriculations d'entreprises.",
        "keywords": ["journal officiel", "jo", "promulgation", "droit congolais", "textes de loi", "arrêtés", "statuts d'entreprises", "législation"]
    },

    # 2. Secteurs Économiques, Fiscaux & Ressources Naturelles
    {
        "id": "finances",
        "name": "Ministère des Finances",
        "category": "Économie, Finances & Secteurs Publics",
        "url": "https://finances.gouv.cd/",
        "domain": "finances.gouv.cd",
        "description": "Gestion macroéconomique, coordination des politiques fiscales nationales, mobilisation des ressources publiques et relations avec les institutions financières internationales.",
        "keywords": ["finances", "fiscalité", "trésor public", "recettes de l'état", "politique fiscale", "dette publique", "budget"]
    },
    {
        "id": "budget",
        "name": "Ministère du Budget",
        "category": "Économie, Finances & Secteurs Publics",
        "url": "https://budget.gouv.cd/",
        "domain": "budget.gouv.cd",
        "description": "Gestion des dépenses publiques, élaboration du cadre budgétaire national, loi de finances et lois d'exécution budgétaire de l'État.",
        "keywords": ["budget", "loi de finances", "dépenses publiques", "crédits budgétaires", "solde", "exécution du budget"]
    },
    {
        "id": "mines",
        "name": "Ministère des Mines",
        "category": "Économie, Finances & Secteurs Publics",
        "url": "https://mines.gouv.cd/",
        "domain": "mines.gouv.cd",
        "description": "Réglementation, octroi de licences, cadastre minier et administration du secteur minier congolais (cuivre, cobalt, coltan, or).",
        "keywords": ["mines", "minier", "cadastre minier", "cobalt", "cuivre", "coltan", "permis d'exploitation", "redevance minière"]
    },
    {
        "id": "hydrocarbures",
        "name": "Ministère des Hydrocarbures",
        "category": "Économie, Finances & Secteurs Publics",
        "url": "https://hydrocarbures.gouv.cd/",
        "domain": "hydrocarbures.gouv.cd",
        "description": "Régulation de l'exploration, raffinage, attribution des blocs pétroliers et gaziers, et distribution des produits pétroliers.",
        "keywords": ["hydrocarbures", "pétrole", "gaz", "blocs pétroliers", "carburant", "raffinage", "distribution pétrolière"]
    },
    {
        "id": "economie",
        "name": "Ministère de l'Économie Nationale",
        "category": "Économie, Finances & Secteurs Publics",
        "url": "https://economie.gouv.cd/",
        "domain": "economie.gouv.cd",
        "description": "Surveillance de la concurrence, contrôle et fixation des prix intérieurs, politique des prix et structuration du commerce national.",
        "keywords": ["économie", "prix", "concurrence", "marché intérieur", "commerce intérieur", "tarification", "inflation"]
    },
    {
        "id": "bcc",
        "name": "Banque Centrale du Congo (BCC)",
        "category": "Économie, Finances & Secteurs Publics",
        "url": "https://bcc.cd",
        "domain": "bcc.cd",
        "description": "Autorité monétaire centrale émettrice du Franc Congolais (CDF), régulation du système bancaire, taux de change officiels et politique monétaire.",
        "keywords": ["banque centrale", "bcc", "franc congolais", "cdf", "taux de change", "devises", "banques", "politique monétaire"]
    },

    # 3. Fonction Publique, Recettes & Agences de Régulation
    {
        "id": "fonction-publique",
        "name": "Ministère de la Fonction Publique",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://fonctionpublique.gouv.cd/",
        "domain": "fonctionpublique.gouv.cd",
        "description": "Gestion des effectifs des agents et fonctionnaires de l'État, numérisation du fichier de la paie, modernisation administrative et carrières publiques.",
        "keywords": ["fonction publique", "fonctionnaire", "agent public", "paie de l'etat", "recrutement public", "retraite", "matricule"]
    },
    {
        "id": "dgi",
        "name": "Direction Générale des Impôts (DGI)",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://dgi.gouv.cd/",
        "domain": "dgi.gouv.cd",
        "description": "Administration fiscale nationale : déclarations fiscales, numéros impôt (NIF), impôt professionnel sur les rémunérations (IPR), TVA et taxes intérieures.",
        "keywords": ["dgi", "impôt", "impôts", "tva", "nif", "déclaration fiscale", "numéro impôt", "taxes", "fiscalité"]
    },
    {
        "id": "dgda",
        "name": "Direction Générale des Douanes et Accises (DGDA)",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://douane.gouv.cd/",
        "domain": "douane.gouv.cd",
        "description": "Administration douanière : dédouanement des marchandises, droits de douane à l'import-export, accises, passages frontaliers et guichet unique douanier.",
        "keywords": ["douane", "dgda", "dédouanement", "importation", "exportation", "tarif douanier", "frontière", "droits d'accises"]
    },
    {
        "id": "anapi",
        "name": "ANAPI (Agence Nationale pour la Promotion des Investissements)",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://anapi.cd",
        "domain": "anapi.cd",
        "description": "Guichet de facilitation des investissements, création d'entreprises, incitations fiscales et douanières du Code des Investissements.",
        "keywords": ["anapi", "investissements", "investir en rdc", "code des investissements", "création entreprise", "agrément"]
    },
    {
        "id": "arsp",
        "name": "ARSP (Autorité de Régulation de la Sous-Traitance dans le Secteur Privé)",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://arsp.cd",
        "domain": "arsp.cd",
        "description": "Régulation et promotion du contenu local : contrôle de l'application de la loi sur la sous-traitance réservée aux entreprises à capitaux congolais.",
        "keywords": ["arsp", "sous-traitance", "contenu local", "entreprises congolaises", "marchés privés", "attestation arsp"]
    },
    {
        "id": "occ",
        "name": "OCC (Office Congolais de Contrôle)",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://occ.cd",
        "domain": "occ.cd",
        "description": "Organisme national de contrôle de conformité, normes de qualité des produits, analyses en laboratoire, métrologie et sécurité des denrées importées/exportées.",
        "keywords": ["occ", "contrôle qualité", "normes", "inspection", "laboratoire", "conformité", "certification"]
    },
    {
        "id": "arptc",
        "name": "ARPTC (Autorité de Régulation des Postes et des Télécommunications)",
        "category": "Fonction Publique, Recettes & Régulation",
        "url": "https://arptc.gouv.cd/",
        "domain": "arptc.gouv.cd",
        "description": "Régulation des télécommunications, fréquences hertziennes, connectivité internet, protection des données personnelles et secteur postal.",
        "keywords": ["arptc", "télécommunications", "internet", "fréquences", "opérateurs télécoms", "postes", "régulation numérique"]
    },

    # 4. Administration Civile, Sécurité, Justice & Élections
    {
        "id": "interieur",
        "name": "Ministère de l'Intérieur, Sécurité et Décentralisation",
        "category": "Administration Civile, Sécurité & Justice",
        "url": "https://interieur.gouv.cd/",
        "domain": "interieur.gouv.cd",
        "description": "Coordination de la Police Nationale Congolaise (PNC), administration territoriale et provinciale, maintien de l'ordre public et affaires coutumières.",
        "keywords": ["intérieur", "police", "pnc", "sécurité", "provinces", "gouverneurs", "ordre public", "état civil"]
    },
    {
        "id": "communication",
        "name": "Ministère de la Communication et Médias",
        "category": "Administration Civile, Sécurité & Justice",
        "url": "https://communication.gouv.cd",
        "domain": "communication.gouv.cd",
        "description": "Porte-parole officiel du Gouvernement, régulation des médias audiovisuels et de presse écrite, accréditations des journalistes et communication de l'État.",
        "keywords": ["communication", "médias", "porte-parole", "briefing presse", "journalistes", "presse", "audiovisuel"]
    },
    {
        "id": "affaires-etrangeres",
        "name": "Ministère des Affaires Étrangères",
        "category": "Administration Civile, Sécurité & Justice",
        "url": "https://www.diplomatie.gouv.cd",
        "domain": "diplomatie.gouv.cd",
        "description": "Direction de la diplomatie congolaise, passeports biométriques ordinaires, traités internationaux, ambassades et consulats de la RDC.",
        "keywords": ["affaires étrangères", "diplomatie", "passeport", "ambassade", "consulat", "coopération internationale", "visa diplomatique"]
    },
    {
        "id": "justice",
        "name": "Ministère de la Justice et Garde des Sceaux",
        "category": "Administration Civile, Sécurité & Justice",
        "url": "https://minjustice-rdc.com",
        "domain": "minjustice-rdc.com",
        "description": "Administration judiciaire, parquets et tribunaux, services pénitentiaires, casier judiciaire, légalisation de documents et droits humains.",
        "keywords": ["justice", "tribunaux", "magistrats", "garde des sceaux", "casier judiciaire", "prison", "notariat"]
    },
    {
        "id": "ceni",
        "name": "CENI (Commission Électorale Nationale Indépendante)",
        "category": "Administration Civile, Sécurité & Justice",
        "url": "https://ceni.cd",
        "domain": "ceni.cd",
        "description": "Institution constitutionnelle indépendante en charge des élections, de l'enrôlement des électeurs, de la cartographie électorale et des scrutins nationaux.",
        "keywords": ["ceni", "élections", "scrutin", "carte d'électeur", "vote", "résultats électoraux", "candidatures", "enrôlement"]
    },

    # 5. Santé, Éducation, Agriculture, Tourisme & Données Publiques
    {
        "id": "sante",
        "name": "Ministère de la Santé Publique, Hygiène et Prévention",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://sante.gouv.cd/",
        "domain": "sante.gouv.cd",
        "description": "Politique nationale de santé, couverture santé universelle (CSU), hôpitaux publics, vaccination, surveillance épidémiologique et gratuité de la maternité.",
        "keywords": ["santé", "hôpital", "maternité gratuite", "vaccination", "csu", "médicaments", "épidémie", "soins de santé"]
    },
    {
        "id": "education-nationale",
        "name": "Ministère de l'Éducation Nationale",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://edu-nc.gouv.cd/",
        "domain": "edu-nc.gouv.cd",
        "description": "Enseignement primaire, secondaire et technique, gratuité de l'enseignement fondamental, calendrier scolaire, épreuves de l'EXETAT et diplômes d'État.",
        "keywords": ["éducation", "école", "primaire", "secondaire", "exetat", "gratuité de l'enseignement", "diplôme d'état", "enseignants"]
    },
    {
        "id": "esu",
        "name": "Ministère de l'Enseignement Supérieur et Universitaire (ESU)",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://esu.gouv.cd/",
        "domain": "esu.gouv.cd",
        "description": "Gestion des universités publiques et instituts supérieurs, système LMD, homologation des diplômes académiques et recherche scientifique.",
        "keywords": ["esu", "université", "institut supérieur", "lmd", "étudiants", "professeurs", "diplôme universitaire", "académique"]
    },
    {
        "id": "agriculture",
        "name": "Ministère de l'Agriculture",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://agriculture.gouv.cd/",
        "domain": "agriculture.gouv.cd",
        "description": "Programmes de sécurité alimentaire, développement rural, soutien aux producteurs agricoles, filières vivrières et agro-industrie.",
        "keywords": ["agriculture", "agricole", "sécurité alimentaire", "champs", "semences", "production vivrière", "rural"]
    },
    {
        "id": "tourisme",
        "name": "Ministère du Tourisme",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://tourisme.gouv.cd",
        "domain": "tourisme.gouv.cd",
        "description": "Promotion touristique, parcs nationaux (ICCN), réglementation hôtelière, visas touristiques et valorisation du patrimoine naturel et culturel.",
        "keywords": ["tourisme", "parcs nationaux", "iccn", "hôtels", "voyage rdc", "visiter le congo", "patrimoine"]
    },
    {
        "id": "ins",
        "name": "Institut National de la Statistique (INS)",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://ins.gouv.cd/",
        "domain": "ins.gouv.cd",
        "description": "Collecte, traitement et publication des statistiques nationales, indices des prix à la consommation, données démographiques et enquêtes de l'État.",
        "keywords": ["ins", "statistique", "recensement", "démographie", "indice des prix", "inflation officielle", "données économiques"]
    },
    {
        "id": "evisa",
        "name": "Portail Officiel d'e-Visa RDC",
        "category": "Santé, Éducation & Infrastructure Civique",
        "url": "https://evisa.gouv.cd/",
        "domain": "evisa.gouv.cd",
        "description": "Système sécurisé officiel de demande, suivi et délivrance en ligne des visas électroniques d'entrée en République Démocratique du Congo (Direction Générale de Migration).",
        "keywords": ["evisa", "e-visa", "visa en ligne", "visa rdc", "entrée congo", "dgm visa", "immigration", "passeport visa"]
    }
]

# Map of exact whitelisted domains for search scoping
OFFICIAL_DOMAINS_WHITELIST: List[str] = [
    portal["domain"] for portal in OFFICIAL_DRC_PORTALS
]


def find_matching_official_portals(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Returns exact matching official portals based on keywords in user query.
    Used during RAG context construction to guarantee exact government source attribution.
    """
    q_lower = query.lower()
    matches = []

    for portal in OFFICIAL_DRC_PORTALS:
        score = 0
        if portal["name"].lower() in q_lower:
            score += 10
        if portal["id"] in q_lower or portal["domain"] in q_lower:
            score += 8
        for kw in portal["keywords"]:
            if kw in q_lower:
                score += 3
        if portal["category"].lower() in q_lower:
            score += 1

        if score > 0:
            matches.append((score, portal))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in matches[:max_results]]


def get_all_portals_grouped() -> Dict[str, List[Dict[str, Any]]]:
    """Returns all 30 portals grouped by category for the directory view."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for p in OFFICIAL_DRC_PORTALS:
        cat = p["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(p)
    return grouped

