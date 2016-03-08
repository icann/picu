U_BUFFER_OVERFLOW_ERROR = 15


U_FOLD_CASE_DEFAULT = 0
U_FOLD_CASE_EXCLUDE_SPECIAL_I = 1

UCHAR_BINARY_START = 0
UCHAR_BINARY_LIMIT = 57
U_SHORT_PROPERTY_NAME = 0
U_LONG_PROPERTY_NAME = 1

# enum UPropertyEnum
UCHAR_INVALID_CODE = -1

# enum UNormalization2Mode
UNORM2_COMPOSE = 0
UNORM2_DECOMPOSE = 1
UNORM2_FCD = 2
UNORM2_COMPOSE_CONTIGUOUS = 3


# enum UCharNameChoice
U_UNICODE_CHAR_NAME = 0
U_UNICODE_10_CHAR_NAME = 1 # deprecated as
U_EXTENDED_CHAR_NAME = 2
U_CHAR_NAME_ALIAS = 3


# IDNA option bit set values
UIDNA_USE_STD3_RULES = 2
UIDNA_CHECK_BIDI = 4
UIDNA_CHECK_CONTEXTJ = 8
UIDNA_NONTRANSITIONAL_TO_ASCII = 0x10
UIDNA_NONTRANSITIONAL_TO_UNICODE = 0x20
UIDNA_CHECK_CONTEXTO = 0x40


UIDNA_ERROR_EMPTY_LABEL = 1
UIDNA_ERROR_LABEL_TOO_LONG = 2
UIDNA_ERROR_DOMAIN_NAME_TOO_LONG = 4
UIDNA_ERROR_LEADING_HYPHEN = 8
UIDNA_ERROR_TRAILING_HYPHEN = 0x10
UIDNA_ERROR_HYPHEN_3_4 = 0x20
UIDNA_ERROR_LEADING_COMBINING_MARK = 0x40
UIDNA_ERROR_DISALLOWED = 0x80
UIDNA_ERROR_PUNYCODE = 0x100
UIDNA_ERROR_LABEL_HAS_DOT = 0x200
UIDNA_ERROR_INVALID_ACE_LABEL = 0x400
UIDNA_ERROR_BIDI = 0x800
UIDNA_ERROR_CONTEXTJ = 0x1000
UIDNA_ERROR_CONTEXTO_PUNCTUATION = 0x2000  # Stable ICU 49
UIDNA_ERROR_CONTEXTO_DIGITS = 0x4000  # Stable ICU 49
