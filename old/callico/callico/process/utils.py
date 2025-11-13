def get_entity_display_string(type, instruction, group=""):
    if group:
        group += " > "

    return f"{group}{instruction} ({type})"
