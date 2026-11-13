"""Model-generated conversation without stored greeting templates."""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from .conversation_history import model_history
from .geographic_scope import DRC_SCOPE_INSTRUCTIONS


def conversation_messages(query, language='fr', history=None):
    language_name = {'fr': 'français', 'en': 'English', 'ln': 'lingala', 'sw': 'kiswahili'}.get(language, 'français')
    messages = [SystemMessage(content=DRC_SCOPE_INSTRUCTIONS + '\n' + (
        f'Réponds en {language_name}. Tu es RDC Agent du peuple, un assistant qui aide à comprendre '
        'les services publics en RDC. Réponds naturellement au message et au contexte de la conversation. '
        'Sois bref pour une salutation ou un remerciement. Évite les présentations répétitives, les slogans '
        'et les réponses toutes faites. Ne prétends pas être une administration ni avoir déposé une demande. '
        'Les messages précédents permettent de comprendre la conversation, sans constituer des sources officielles.'
    ))]
    for turn in model_history(history or []):
        cls = HumanMessage if turn['role'] == 'user' else AIMessage
        messages.append(cls(content=turn['content']))
    messages.append(HumanMessage(content=query))
    return messages
