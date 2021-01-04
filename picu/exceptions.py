from . import constants


class PICUException(Exception):
    pass


class IllegalArgument(PICUException):
    pass


class PropertyNotFound(PICUException):
    pass


class IDNAException(PICUException, UnicodeError):
    ERROR_MESSAGES = dict(
        (getattr(constants, e), e) for e in dir(constants) if e.startswith('UIDNA_ERROR_'))

    def __init__(self, idna_errors, obj, msgprefix, *args):
        self.idna_errors = idna_errors
        self.error_labels = []
        self.obj = obj

        # parse IDNA error codes
        for ecode, elabel in self.ERROR_MESSAGES.items():
            if idna_errors & ecode:
                self.error_labels.append(elabel)
                idna_errors = idna_errors & ~ecode
        if idna_errors:
            self.error_labels.append("UNKNOWN_ERROR-%s" % idna_errors)

        super(IDNAException, self).__init__("%s%s" % (msgprefix, ', '.join(self.error_labels)),
                                            *args)
