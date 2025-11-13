from django.core.management.commands import makemessages


class Command(makemessages.Command):
    """
    Override Django makemessages command to add the sort option
    for the underlying Unix tool msgmerge
    """

    msgmerge_options = makemessages.Command.msgmerge_options + ["-s"]
