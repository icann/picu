#!/usr/bin/env python

import sys
from ctypes import cdll, c_char_p, c_int, c_int8, c_uint8, c_int16, c_uint16, c_uint32, c_int32, c_void_p, POINTER, pointer, byref, create_string_buffer, sizeof, Structure
import re
from functools import wraps
from picu import finalize
from picu.utils import memoized, memoized_property
from picu.exceptions import *
from picu.constants import *


UChar32 = c_int32
UChar32_p = POINTER(UChar32)
UCharArray_Single = c_uint16 * 1
UBool = c_int8
UChar = c_uint16
UChar_p = c_void_p
UErrorCode = c_int
UErrorCode_p = POINTER(UErrorCode)
VersionInfo = c_uint8 * 4
c_int32_p = POINTER(c_int32)

# Declare some compats variables
if sys.version_info.major > 2:
    text_type = str
    long = int
    xrange = range
else:
    text_type = basestring

if sys.maxunicode > 65535:
    wide_unichr = chr if sys.version_info.major > 2 else unichr
else:
    def wide_unichr(ord):
        if ord > 0xffff:
            return (r'\U%08X' % ord).decode('unicode-escape')
        else:
            r_chr = chr if sys.version_info.major > 2 else unichr
            return r_chr(ord)


class UIDNAInfo(Structure):
    _fields_ = [("size", c_int16),
                ("isTransitionalDifferent", UBool),
                ("reservedB3", UBool),
                ("errors", c_uint32),
                ("reservedI2", c_int32),
                ("reservedI3", c_int32)]


def new_UIDNAInfo():
    return UIDNAInfo(sizeof(UIDNAInfo), 0, 0, 0, 0, 0)


def U_SUCCESS(err_code):
    return err_code <= 0


def cp_to_uchar_array(cp):
    return UCharArray_Single(cp)


def uchar_array_to_uni(arr, len=None):
    return u''.join(wide_unichr(c) for (i, c) in enumerate(arr) if (len is None or i < len))


def uchar_p_to_uni(arr, len=None):
    return u''.join(wide_unichr(arr[i]) for i in range(len.value))


def str_to_uchar_array_with_len(s):
    slen = len(s)
    UCharArray = c_uint16 * slen
    return UCharArray(*(ord(c) for c in s)), slen


def uchar_array(alen):
    UCharArray = c_uint16 * alen
    return UCharArray(), alen


def str_to_uchar_array(s):
    return str_to_uchar_array_with_len(s)[0]


def icu_re_factory(icu):
    class _ICUMatchObject(object):
        def __init__(self, regex):
            self._regex = regex
            self._matched_groups = None
            self._matched_groups1 = None

        def groups(self):
            """ ICU regex does not seem to support the notion of a group that did not participate in a match.
                In those circumstances, it simply return the empty string so we can't tell.
                This is why we don't accept a `default` argument.
            """
            if not self._matched_groups:
                out = []
                ngroups = icu.uregex_groupCount(self._regex._icu_regex)
                for i in xrange(ngroups+1):
                    destlen = self._regex._input_str_data_len
                    dest = uchar_array(destlen)[0]
                    matchstr_len = icu.uregex_group(self._regex._icu_regex, i, dest, destlen)
                    assert matchstr_len >= 0
                    out.append(uchar_array_to_uni(dest, matchstr_len))
                self._matched_groups = tuple(out)
            return self._matched_groups[1:]

        def _get_matched_groups(self):
            out = []
            ngroups = icu.uregex_groupCount(self._regex._icu_regex)
            for i in xrange(ngroups+1):
                start_i = icu.uregex_start(self._regex._icu_regex, i)
                end_i = icu.uregex_end(self._regex._icu_regex, i)
                out.append((start_i, end_i))
            self._matched_groups = tuple(out)

        def span(self, group=0):
            return self._matched_groups1[group][:2]

        def start(self):
            return icu.uregex_start(self._regex._icu_regex, 0)

    class _ICURegex(object):
        """
        http://icu-project.org/apiref/icu4c/uregex_8h.html
        """

        def __init__(self, _icu_regex):
            # `_regex` is a `URegularExpression*`
            self._icu_regex = _icu_regex
            finalize.track_for_finalization(self, self._icu_regex, icu.uregex_close)

        @property
        def pattern(self):
            patlength = c_int32()
            pat_arr = icu.uregex_pattern(self._icu_regex, pointer(patlength))
            return uchar_p_to_uni(pat_arr, patlength)

        def match(self, string, flags=0, index=0):
            # we always do an implicit clone
            regex = self.clone(string)
            r = icu.uregex_lookingAt(regex._icu_regex, index)
            if r:
                return _ICUMatchObject(regex)
            else:
                return None

        def search(self, string, flags=0, index=0):
            # we always do an implicit clone
            regex = self.clone(string)
            r = icu.uregex_find(regex._icu_regex, index)
            if r:
                return _ICUMatchObject(regex)
            else:
                return None

        def _settext(self, text):
            # a wrapper around `uregex_setText` that retains a reference to the UChar array to prevent it from being
            # garbage collected.
            self._input_text = text
            self._input_str_data, self._input_str_data_len = str_to_uchar_array_with_len(text) # retain reference
            icu.uregex_setText(self._icu_regex, self._input_str_data, self._input_str_data_len)

        def clone(self, text=None):
            regex = _ICURegex(icu.uregex_clone(self._icu_regex))
            if text is not None:
                regex._settext(text)
            return regex

    class _ICURegexModuleAPI(object):
        """ This should quack like the built-in `re` module. """
        @classmethod
        def compile(cls, pattern, flags=0):
            # TODO: pass in UParseError argument to get better diagnostics
            args = str_to_uchar_array_with_len(pattern) + (flags, None)
            try:
                regex = icu.uregex_open(*args)
                return _ICURegex(regex)
            except PICUException as e:
                raise re.error(str(e))

        @classmethod
        def match(cls, pattern, string, flags=0):
            return cls.compile(pattern, flags).match(string)

        @classmethod
        def search(cls, pattern, string, flags=0):
            regex = cls.compile(pattern, flags)
            return regex.search(string)

    return _ICURegexModuleAPI


def icu_set_factory(icu):
    class _ICUSet(object):
        """
        See http://userguide.icu-project.org/strings/unicodeset

        :param iterable: an `_ICUSet` or any collection of integers (code points)
        """
        def __init__(self, iterable=None, pattern=None, freeze=False):
            if iterable and pattern:
                raise IllegalArgument("specify iterable or pattern, but not both")

            # we can't use `isinstance` because it is dynamically defined
            # and each _ICUSet might be instantiated from a different `ICUCommon` object
            self.__is_icuset = True

            self._uset = None

            try:
                if iterable:
                    if getattr(iterable, '__is_icuset', False):
                        # if this is an _ICUSet, clone it
                        self._uset = icu.uset_cloneAsThawed(iterable._uset)
                    elif hasattr(iterable, '__iter__'):
                        self._uset = icu.uset_openEmpty()
                        for cp in iterable:
                            self.add(cp)
                    elif isinstance(iterable, int):
                        # another uset
                        self._uset = iterable
                    else:
                        raise IllegalArgument('iterable must be either another ICUSet object or a list of ints')
                elif pattern:
                    self._uset = icu.uset_openPattern(*str_to_uchar_array_with_len(pattern))
                else:
                    self._uset = icu.uset_openEmpty()
            finally:
                if self._uset:
                    # take ownership
                    finalize.track_for_finalization(self, self._uset, icu.uset_close)

            if freeze:
                self.freeze()

        def freeze(self):
            icu.uset_freeze(self._uset)

        def is_frozen(self):
            return bool(icu.uset_isFrozen(self._uset))

        def add(self, cp):
            assert not self.is_frozen(), "cannot modify frozen set"
            if not isinstance(cp, (int, long)):
                raise ValueError("%r is not an integer" % (cp,))
            icu.uset_add(self._uset, cp)

        def update(self, other):
            assert not self.is_frozen(), "cannot modify frozen set"
            if getattr(other, '__is_icuset', False):
                icu.uset_addAll(other._uset)
            else:
                for i in other:
                    icu.uset_add(self._uset, i)

        def remove(self, cp):
            assert not self.is_frozen(), "cannot modify frozen set"
            icu.uset_remove(self._uset, cp)

        def __len__(self):
            return icu.uset_size(self._uset)

        def __iter__(self):
            for cp_start, cp_end in self.ranges():
                for cp in range(cp_start, cp_end+1):
                    yield cp

        def ranges(self):
            for i in range(icu.uset_getItemCount(self._uset)):
                cp_start = UChar32(0)
                cp_end = UChar32(0)
                rv = icu.uset_getItem(self._uset, i, pointer(cp_start), pointer(cp_end), None, 0)
                # XXX: we don't support string items
                assert rv == 0, "we only support ranges"
                yield cp_start.value, cp_end.value

        def __contains__(self, cp):
            if isinstance(cp, int):
                return icu.uset_contains(self._uset, cp)
            elif isinstance(cp, text_type) and len(cp) == 1:
                return icu.uset_contains(self._uset, ord(cp[0]))
            else:
                raise IllegalArgument("cp must be an integer or a single unicode character")

        def __and__(self, other):
            newset = icu.uset_cloneAsThawed(self._uset)
            icu.uset_retainAll(newset, other._uset)
            return self.__class__(newset)

        def __or__(self, other):
            newset = icu.uset_cloneAsThawed(self._uset)
            icu.uset_addAll(newset, other._uset)
            return self.__class__(newset)

        def __sub__(self, other):
            newset = icu.uset_cloneAsThawed(self._uset)
            icu.uset_removeAll(newset, other._uset)
            return self.__class__(newset)

        def complement(self):
            """
            ICU's complement method. This is destructive, and will modify the set
            """
            assert not self.is_frozen(), "cannot modify frozen set"
            icu.uset_complement(self._uset)

        def __unicode__(self):
            err = UErrorCode(0)
            destlen = icu.uset_toPattern_raw(self._uset, None, 0, 1, pointer(err))
            dest = uchar_array(destlen)[0]
            err = UErrorCode(0)
            rv = icu.uset_toPattern_raw(self._uset, dest, destlen, 1, pointer(err))
            return uchar_array_to_uni(dest[:rv])

        __str__ = __unicode__

        # we always do deepcopy
        def __copy__(self):
            return self.__class__(uset2)
        __deepcopy__ = __copy__
        copy = __copy__

    return _ICUSet


class ICUProperty(object):
    def __init__(self, icu, propname_enum):
        self.enum = propname_enum
        self._icu = icu

    def __unicode__(self):
        return self.name

    __str__ = __unicode__

    @property
    def name(self):
        if not hasattr(self, '_name'):
            self._name = self._icu.getPropertyName(self.enum, U_LONG_PROPERTY_NAME)
        return self._name

    @property
    def shortname(self):
        if not hasattr(self, '_shortname'):
            self._shortname = self._icu.getPropertyName(self.enum, U_SHORT_PROPERTY_NAME)
        return self._shortname


class ICUCommon(object):
    def __init__(self, uc_dll, i18n_dll, ver):
        self.uc_dll = uc_dll
        self.i18n_dll = i18n_dll
        self.ver = ver
        self.std_icu_func(self._getfunc('u_init', (UErrorCode_p,)))()

    def isBinaryProp(self, prop):
        return prop >= UCHAR_BINARY_START and prop < UCHAR_BINARY_LIMIT

    def std_icu_func(self, f):
        @wraps(f)
        def wrapper(*args):
            err = c_int(0)
            rv = f(*(args + (pointer(err),)))
            if err.value > 0:
                #import ipdb; ipdb.set_trace()
                # success is 0, warnings negative, errors are positive
                raise PICUException("%s failed with error code %d (%s)" % (f.__name__, err.value, self.u_errorName(err)))
            return rv
        return wrapper

    @property
    @memoized
    def u_errorName(self):
        return self._getfunc('u_errorName', (UErrorCode,), c_char_p)

    @property
    @memoized
    def set(self):
        return icu_set_factory(self)

    @property
    @memoized
    def re(self):
        return icu_re_factory(self)

    @property
    @memoized
    def getPropertyEnum(self):
        return self._getfunc('u_getPropertyEnum', (c_char_p,), c_int)

    @property
    @memoized
    def getIntPropertyValue(self):
        return self._getfunc("u_getIntPropertyValue")

    @property
    @memoized
    def getPropertyName(self):
        return self._getfunc('u_getPropertyName', (UErrorCode,), c_char_p)

    @property
    @memoized
    def getPropertyValueName(self):
        return self._getfunc("u_getPropertyValueName", restype=c_char_p)

    @property
    @memoized
    def getPropertyValueEnum(self):
        return self._getfunc("u_getPropertyValueEnum", restype=c_int)

    @property
    def getScriptExtensions(self):
        return self._getfunc("uscript_getScriptExtensions", restype=c_int)

    @property
    @memoized
    def getCombiningClass(self):
        return self._getfunc("u_getCombiningClass", restype=c_int8)

    @property
    def scriptIsRightToLeft(self):
        return self._getfunc("uscript_isRightToLeft", restype=UBool)

    @property
    @memoized
    def isDigit(self):
        return self._getfunc("u_isdigit", restype=UBool)

    @memoized_property
    def _u_charName(self):
        # int32_t u_charName (UChar32 code, UCharNameChoice nameChoice, char *buffer, int32_t bufferLength, UErrorCode *pErrorCode)
        return self._getfunc('u_charName',
                             (UChar32, c_int, c_char_p, c_int32, UErrorCode_p),
                             c_int32)

    @memoized_property
    def u_charName(self):
        return self.std_icu_func(self._u_charName)

    def charName(self, cp, option=U_UNICODE_CHAR_NAME):
        err = UErrorCode(0)
        rv = self._u_charName(cp, option, None, 0, pointer(err))
        if rv == 0:
            return u""

        dest, destlen = create_string_buffer(rv+1), rv # allocate the right amount of buffer
        self.u_charName(cp, option, dest, destlen+1)
        return dest.value.decode('ascii')

    def charAge(self, cp):
        func = getattr(self.uc_dll, "u_charAge_%s" % self.ver)
        ver = VersionInfo()
        func(cp, pointer(ver))
        return '.'.join(str(v) for v in ver)

    def getUnicodeVersion(self):
        func = getattr(self.uc_dll, "u_getUnicodeVersion_%s" % self.ver)
        ver = VersionInfo()
        func(pointer(ver))
        return '.'.join(str(v) for v in ver[:3])

    #### USet ####
    @property
    def uset_openPattern(self):
        return self.std_icu_func(self._getfunc('uset_openPattern',
                                               (c_void_p, c_int32, POINTER(c_int)),
                                               c_void_p))

    @property
    def uset_openEmpty(self):
        return self._getfunc('uset_openEmpty', None, c_void_p)

    @property
    def uset_close(self):
        return self._getfunc('uset_close', (c_void_p,), c_void_p)

    @property
    def uset_clone(self):
        return self._getfunc('uset_clone', (c_void_p,), c_void_p)

    @property
    def uset_cloneAsThawed(self):
        return self._getfunc('uset_cloneAsThawed', (c_void_p,), c_void_p)

    @property
    def uset_freeze(self):
        return self._getfunc('uset_freeze', (c_void_p,))

    @property
    def uset_isFrozen(self):
        return self._getfunc('uset_isFrozen', (c_void_p,), UBool)

    @memoized_property
    def uset_remove(self):
        # void uset_remove(USet *set, UChar32 c)
        return self._getfunc('uset_remove', (c_void_p, UChar32))

    @memoized_property
    def uset_add(self):
        # void uset_add(USet *set, UChar32 c)
        return self._getfunc('uset_add', (c_void_p, UChar32))

    @memoized_property
    def uset_getItem(self):
        # int32_t uset_getItem(const USet *set, int32_t itemIndex, UChar32 *start, UChar32 *end, UChar *str, int32_t strCapacity, UErrorCode *ec)
        return self.std_icu_func(
            self._getfunc('uset_getItem',
                          (c_void_p, c_int32, UChar32_p, UChar32_p, UChar_p, c_int32, UErrorCode_p),
                          c_int32))

    @memoized_property
    def uset_getItemCount(self):
        # int32_t uset_getItemCount(const USet *set)
        return self._getfunc('uset_getItemCount', (c_void_p,), c_int32)

    @property
    def uset_addAll(self):
        return self._getfunc('uset_addAll', (c_void_p, c_void_p))

    @property
    def uset_removeAll(self):
        return self._getfunc('uset_removeAll', (c_void_p, c_void_p))

    @property
    def uset_retainAll(self):
        return self._getfunc('uset_retainAll', (c_void_p, c_void_p))

    @property
    def uset_contains(self):
        return self._getfunc('uset_contains', (c_void_p, UChar32), UBool)

    @property
    def uset_size(self):
        return self._getfunc('uset_size', (c_void_p,), c_int32)

    @property
    def uset_complement(self):
        return self._getfunc('uset_complement', (c_void_p,), None)

    @memoized_property
    def uset_toPattern_raw(self):
        # int32_t uset_toPattern(const USet *set, UChar *result, int32_t resultCapacity, UBool escapeUnprintable, UErrorCode *ec)
        return self._getfunc('uset_toPattern',
                             (c_void_p, UChar_p, c_int32, UBool, UErrorCode_p),
                             c_int32)

    #### URegex ####
    @property
    @memoized
    def uregex_open(self):
        # (const UChar *pattern, int32_t patternLength, uint32_t flags, UParseError *pe, UErrorCode *status) -> URegularExpression *
        return self.std_icu_func(self._getfunc('uregex_open',
                                               (UChar_p, c_int32, c_uint32, c_void_p, UErrorCode_p), c_void_p,
                                               dll=self.i18n_dll))

    @property
    @memoized
    def uregex_close(self):
        return self._getfunc('uregex_close', (c_void_p,), dll=self.i18n_dll)

    @property
    @memoized
    def uregex_clone(self):
        # (const URegularExpression *regexp, UErrorCode *status) ->  -> URegularExpression *
        return self.std_icu_func(self._getfunc('uregex_clone',
                                               (c_void_p, UErrorCode_p), c_void_p,
                                               dll=self.i18n_dll))


    @property
    @memoized
    def uregex_setText(self):
        # (URegularExpression *regexp, const UChar *text, int32_t textLength, UErrorCode *status) -> void
        return self.std_icu_func(self._getfunc('uregex_setText',
                                               (c_void_p, UChar_p, c_int32, UErrorCode_p),
                                               dll=self.i18n_dll))

    @property
    @memoized
    def uregex_lookingAt(self):
        # (URegularExpression *regexp, int32_t startIndex, UErrorCode *status) -> UBool
        return self.std_icu_func(
            self._getfunc('uregex_lookingAt',
                          (c_void_p, c_int32, UErrorCode_p), UBool,
                          dll=self.i18n_dll))

    @memoized_property
    def uregex_find(self):
        # (URegularExpression *regexp, int32_t startIndex, UErrorCode *status) -> UBool
        return self.std_icu_func(
            self._getfunc('uregex_find',
                          (c_void_p, c_int32, UErrorCode_p), UBool,
                          dll=self.i18n_dll))

    @memoized_property
    def uregex_matches(self):
        # (URegularExpression *regexp, int32_t startIndex, UErrorCode *status) -> UBool
        return self.std_icu_func(
            self._getfunc('uregex_matches',
                          (c_void_p, c_int32, UErrorCode_p), UBool,
                          dll=self.i18n_dll))

    @memoized_property
    def uregex_pattern(self):
        #const UChar * 	uregex_pattern (const URegularExpression *regexp, int32_t *patLength, UErrorCode *status)
        return self.std_icu_func(
            self._getfunc('uregex_pattern',
                          (c_void_p, c_int32_p, UErrorCode_p), POINTER(UChar),
                          dll=self.i18n_dll))


    @memoized_property
    def uregex_groupCount(self):
        # int32_t 	uregex_groupCount (URegularExpression *regexp, UErrorCode *status)
        return self.std_icu_func(
            self._getfunc('uregex_groupCount',
                          (c_void_p, UErrorCode_p), c_int32,
                          dll=self.i18n_dll))

    @memoized_property
    def uregex_group(self):
        # int32_t uregex_group(URegularExpression *regexp, int32_t groupNum, UChar *dest, int32_t destCapacity, UErrorCode *status)
        return self.std_icu_func(
            self._getfunc('uregex_group',
                          (c_void_p, c_int32, UChar_p, c_int32, UErrorCode_p), c_int32,
                          dll=self.i18n_dll))

    @memoized_property
    def uregex_start(self):
        # int32_t uregex_start(URegularExpression *regexp, int32_t groupNum, UErrorCode *status)
        return self.std_icu_func(
            self._getfunc('uregex_start',
                          (c_void_p, c_int32, UErrorCode_p), c_int32,
                          dll=self.i18n_dll))

    @memoized_property
    def uregex_end(self):
        # int32_t uregex_end(URegularExpression *regexp, int32_t groupNum, UErrorCode *status)
        return self.std_icu_func(
            self._getfunc('uregex_end',
                          (c_void_p, c_int32, UErrorCode_p), c_int32,
                          dll=self.i18n_dll))

    @memoized
    def _getfunc(self, funcname, argtypes=None, restype=None, dll=None):
        dll = dll or self.uc_dll
        func = getattr(dll, "%s_%s" % (funcname, self.ver))
        if not func:
            raise PICUException("function %s not found" % funcname)
        if argtypes:
            func.argtypes = list(argtypes)
        if restype:
            func.restype = restype
        return func

    #### Normalization ####
    @property
    @memoized
    def getNormalizer(self):
        # use this instead of getNFCInstance and friends because ICU 4.4 didn't have them yet
        return self.std_icu_func(self._getfunc('unorm2_getInstance',
                                          (c_void_p, c_char_p, c_int, UErrorCode_p),
                                          c_void_p))

    @property
    @memoized
    def NFC(self):
        return self.getNormalizer(None, "nfc", UNORM2_COMPOSE)

    @property
    @memoized
    def NFD(self):
        return self.getNormalizer(None, "nfc", UNORM2_DECOMPOSE)

    @property
    @memoized
    def NFKC(self):
        return self.getNormalizer(None, "nfkc", UNORM2_COMPOSE)

    @property
    @memoized
    def NFKD(self):
        return self.getNormalizer(None, "nfkc", UNORM2_DECOMPOSE)

    @property
    @memoized
    def _unorm2_normalize(self):
        return self._getfunc('unorm2_normalize',
                             (c_void_p, UChar_p, c_uint32, UChar_p, c_uint32, UErrorCode_p),
                             c_int)

    @property
    @memoized
    def unorm2_normalize(self):
        return self.std_icu_func(self._unorm2_normalize)

    def isNormalized(self, s, normalizer):
        assert isinstance(s, text_type)
        unorm2_isNormalized = self.std_icu_func(self._getfunc('unorm2_isNormalized',
                                                              (c_void_p, UChar_p, c_uint32, UErrorCode_p),
                                                              UBool))
        return unorm2_isNormalized(normalizer, *str_to_uchar_array_with_len(s))

    def normalize(self, s, normalizer):
        assert isinstance(s, text_type)
        src, srclen = str_to_uchar_array_with_len(s)
        dest, destlen = uchar_array(srclen)
        err = UErrorCode(0)
        rv = self._unorm2_normalize(normalizer, src, srclen, pointer(dest), destlen, pointer(err))
        if err <= 0:
            return uchar_array_to_uni(dest[:rv])

        # need more space
        dest, destlen = uchar_array(rv)
        rv = self.unorm2_normalize(normalizer, src, srclen, pointer(dest), destlen)
        return uchar_array_to_uni(dest[:rv])

    #### Case Folding ####
    @property
    @memoized
    def u_strFoldCase(self):
        return self.std_icu_func(self._getfunc('u_strFoldCase',
                                               (UChar_p, c_int32, UChar_p, c_int32, c_uint32, UErrorCode_p),
                                               c_int32))

    def foldcase(self, s, option=U_FOLD_CASE_DEFAULT):
        assert isinstance(s, text_type)
        src, srclen = str_to_uchar_array_with_len(s)
        dest, destlen = uchar_array(5*srclen) # allocate more space
        rv = self.u_strFoldCase(pointer(dest), destlen, byref(src), srclen, option)
        return uchar_array_to_uni(dest[:rv])

    #### Properties ####
    def property_by_name(self, propname):
        p = self.getPropertyEnum(propname.encode('ascii'))
        if p == UCHAR_INVALID_CODE:
            raise PropertyNotFound("unknown property (%s)" % propname)
        return ICUProperty(self, p)

    def get_prop_value(self, cp, propname, prop_type=U_LONG_PROPERTY_NAME):
        prop = self.property_by_name(propname)
        pv = self.getIntPropertyValue(cp, prop.enum)
        return self.getPropertyValueName(prop.enum, pv, prop_type).decode('ascii')

    def get_script(self, cp, prop_type=U_LONG_PROPERTY_NAME):
        if isinstance(cp, text_type):
            cp = ord(cp)
        return self.get_prop_value(cp, 'Sc', prop_type)

    def get_script_extensions(self, cp, prop_type=U_LONG_PROPERTY_NAME):
        ScriptsArray = c_int * 10
        scripts = ScriptsArray()
        rv = c_int(0)
        n = self.getScriptExtensions(cp, pointer(scripts), 10, pointer(rv))
        if rv.value != 0:
            raise RuntimeError("oh no rv=%d" % rv.value)
        out = []

        script_prop = self.property_by_name('Script')

        for i in range(n):
            out.append(self.getPropertyValueName(script_prop.enum, scripts[i],
                                                 prop_type).decode('utf-8'))

        return out

    def is_combining_mark(self, cp):
        return self.get_prop_value(cp, 'General_Category') in ['Nonspacing_Mark', 'Spacinf_Mark']

    def is_script_rtl(self, script):
        script_prop = self.property_by_name('Script')
        script_enum = self.getPropertyValueEnum(script_prop.enum, script.encode('ascii'))

        return self.scriptIsRightToLeft(script_enum)

    def is_rtl(self, cp):
        script = self.get_script(cp)
        return self.is_script_rtl(script)

    def is_digit(self, cp):
        return self.isDigit(cp)

    #### IDNA ####
    @memoized_property
    def uidna_openUTS46(self):
        return self.std_icu_func(self._getfunc('uidna_openUTS46',
                                               (c_uint32, UErrorCode_p),
                                               c_void_p))

    @memoized_property
    def uidna_close(self):
        return self.std_icu_func(self._getfunc('uidna_close',
                                               (c_void_p,),
                                               None))

    @memoized
    def open_uts46(self, options=UIDNA_USE_STD3_RULES
                                 | UIDNA_CHECK_BIDI
                                 | UIDNA_CHECK_CONTEXTJ
                                 | UIDNA_CHECK_CONTEXTO
                                 | UIDNA_NONTRANSITIONAL_TO_ASCII
                                 | UIDNA_NONTRANSITIONAL_TO_UNICODE):
        uts46 = self.uidna_openUTS46(options)
        finalize.track_for_finalization(self, uts46, self.uidna_close)
        return uts46

    @memoized
    def _get_idna_process_func(self, func_name):
        # The IDNA X-To-Y functions that we use have the following signature
        # (const UIDNA *idna, const UChar *label, int32_t length,
        #  UChar *dest, int32_t capacity, UIDNAInfo *pInfo, UErrorCode *pErrorCode)
        # -> int32_t
        return self._getfunc(func_name,
                             (c_void_p, UChar_p, c_int32, UChar_p, c_int32,
                              c_void_p, UErrorCode_p),
                             c_int32)

    @memoized_property
    def _uidna_labelToASCII(self):
        return self._get_idna_process_func('uidna_labelToASCII')

    @memoized_property
    def uidna_labelToASCII(self):
        return self.std_icu_func(self._uidna_labelToASCII)

    @memoized_property
    def _uidna_labelToUnicode(self):
        return self._get_idna_process_func('uidna_labelToUnicode')

    @memoized_property
    def uidna_labelToUnicode(self):
        return self.std_icu_func(self._uidna_labelToUnicode)


    @memoized_property
    def _uidna_nameToASCII(self):
        return self._get_idna_process_func('uidna_nameToASCII')

    @memoized_property
    def uidna_nameToASCII(self):
        return self.std_icu_func(self._uidna_nameToASCII)

    @memoized_property
    def _uidna_nameToUnicode(self):
        return self._get_idna_process_func('uidna_nameToUnicode')

    @memoized_property
    def uidna_nameToUnicode(self):
        return self.std_icu_func(self._uidna_nameToUnicode)

    def idna_process(self, s, func, _lowlvl_func, uidna=None):
        assert isinstance(s, text_type)
        src, srclen = str_to_uchar_array_with_len(s)
        dest, destlen = uchar_array(64)
        uidna = uidna or self.open_uts46()
        idna_info = new_UIDNAInfo()
        err = UErrorCode(0)
        rv = _lowlvl_func(uidna, src, srclen, pointer(dest), destlen, pointer(idna_info), pointer(err))
        if U_SUCCESS(err.value):
            if idna_info.errors == 0:
                return uchar_array_to_uni(dest[:rv])
            else:
                raise IDNAException(idna_info.errors, s, _lowlvl_func.__name__ + ': ')
        elif err.value != U_BUFFER_OVERFLOW_ERROR:
            raise PICUException("%s failed with error code %d (%s)"
                                % (_lowlvl_func, err.value, self.u_errorName(err)))

        # need more space
        dest, destlen = uchar_array(rv+1)
        idna_info = new_UIDNAInfo()
        rv = func(uidna, src, srclen, pointer(dest), destlen, pointer(idna_info))
        if idna_info.errors == 0:
            return uchar_array_to_uni(dest[:rv])
        else:
            raise IDNAException(idna_info.errors, s, func.__name__ + ': ')

    def idna_encode_label(self, s, uidna=None):
        return self.idna_process(s, self.uidna_labelToASCII, self._uidna_labelToASCII, uidna)

    def idna_decode_label(self, s, uidna=None):
        return self.idna_process(s, self.uidna_labelToUnicode, self._uidna_labelToUnicode, uidna)

    def idna_encode(self, s, uidna=None):
        return self.idna_process(s, self.uidna_nameToASCII, self._uidna_nameToASCII, uidna)

    def idna_decode(self, s, uidna=None):
        return self.idna_process(s, self.uidna_nameToUnicode, self._uidna_nameToUnicode, uidna)


KNOWN_ICU_VERSIONS = (
    '71',
    '70',  # Unicode 14.0
    '69',
    '68',
    '67',  # Unicode 13.0
    '66',
    '65',
    '64',  # Unicode 12.0
    '63',
    '62',  # Unicode 11.0
    '61',
    '60',  # Unicode 10.0
    '59',
    '58',  # Unicode 9.0
    '57',
    '56',  # Unicode 8.0
    '55',
    '54',  # Unicode 7.0
    '53',
    '52',  # Unicode 6.3
    '51',
    '50',  # Unicode 6.2
    '49',  # Unicode 6.1
    '48',
    '46',  # Unicode 6.0  -- min version for IDNA ("Stable since ICU 4.6")
    '44',  # Unicode 5.2
    '40',  # Unicode 5.1
    '36',  # Unicode 5.0
    '34',  # Unicode 4.1
)


def icu_load(libpath='libicuuc.dylib', i18n_libpath='libicui18n.dylib', ver=None):
    uc_dll = cdll.LoadLibrary(libpath)
    i18n_dll = cdll.LoadLibrary(i18n_libpath)

    if not ver:
        # auto detect
        for ver in KNOWN_ICU_VERSIONS:
            try:
                getattr(uc_dll, "u_getUnicodeVersion_%s" % ver)
                break
            except AttributeError:
                pass
        else:
            raise PICUException("could not determine ICU version for %s" % (libpath,))

    return ICUCommon(uc_dll, i18n_dll, ver)
