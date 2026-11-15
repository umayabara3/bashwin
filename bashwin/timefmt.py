# -*- coding: utf-8 -*-
"""OS の strftime に依存しない日時書式(C ロケール固定)。

Windows の CRT は %s %N %-d %e 等を持たないため、date と printf %(...)T は
ここで自前実装し、Linux/Windows で同じ結果を返す。
"""
import datetime
import time

_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
           'September', 'October', 'November', 'December']


def _zone(tm, utc):
    if utc:
        return 'UTC', 0
    off = getattr(tm, 'tm_gmtoff', None)
    if off is None:
        off = -(time.altzone if tm.tm_isdst > 0 else time.timezone)
    name = getattr(tm, 'tm_zone', None) or ''
    try:
        ascii_ok = all(ord(c) < 128 for c in name)
    except TypeError:
        ascii_ok = False
    if not name or not ascii_ok or ' ' in name or len(name) > 6:
        sign = '-' if off < 0 else '+'
        a = abs(off)
        name = '%s%02d' % (sign, a // 3600) + ('%02d' % (a % 3600 // 60) if a % 3600 else '')
    return name, off


def strftime(fmt, epoch=None, utc=False):
    if epoch is None:
        epoch = time.time()
    sec = int(epoch // 1)
    nanos = int(round((epoch - sec) * 1e9))
    if nanos >= 1000000000:
        nanos = 999999999
    tm = time.gmtime(sec) if utc else time.localtime(sec)
    zname, off = _zone(tm, utc)
    wd_sun = (tm.tm_wday + 1) % 7
    h12 = tm.tm_hour % 12 or 12
    out = []
    i = 0
    n = len(fmt)
    while i < n:
        c = fmt[i]
        if c != '%' or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        i += 1
        flag = ''
        while i < n and fmt[i] in '-_0^#':
            flag = fmt[i]
            i += 1
        width = ''
        while i < n and fmt[i].isdigit():
            width += fmt[i]
            i += 1
        colon = False
        if i < n and fmt[i] == ':' and i + 1 < n and fmt[i + 1] == 'z':
            colon = True
            i += 1
        if i >= n:
            out.append('%')
            break
        d = fmt[i]
        i += 1

        def num(v, w, pad='0'):
            if flag == '-':
                return str(v)
            if flag == '_':
                pad = ' '
            elif flag == '0':
                pad = '0'
            w2 = int(width) if width else w
            return str(v).rjust(w2, pad)

        if d == 'Y':
            s = num(tm.tm_year, 4)
        elif d == 'C':
            s = num(tm.tm_year // 100, 2)
        elif d == 'y':
            s = num(tm.tm_year % 100, 2)
        elif d == 'm':
            s = num(tm.tm_mon, 2)
        elif d == 'd':
            s = num(tm.tm_mday, 2)
        elif d == 'e':
            s = num(tm.tm_mday, 2, ' ')
        elif d == 'H':
            s = num(tm.tm_hour, 2)
        elif d == 'I':
            s = num(h12, 2)
        elif d == 'k':
            s = num(tm.tm_hour, 2, ' ')
        elif d == 'l':
            s = num(h12, 2, ' ')
        elif d == 'M':
            s = num(tm.tm_min, 2)
        elif d == 'S':
            s = num(tm.tm_sec, 2)
        elif d == 'N':
            s = '%09d' % nanos
            if width:
                s = s[:int(width)]
        elif d == 's':
            s = str(sec)
        elif d == 'j':
            s = num(tm.tm_yday, 3)
        elif d == 'a':
            s = _DAYS[tm.tm_wday][:3]
        elif d == 'A':
            s = _DAYS[tm.tm_wday]
        elif d == 'b' or d == 'h':
            s = _MONTHS[tm.tm_mon - 1][:3]
        elif d == 'B':
            s = _MONTHS[tm.tm_mon - 1]
        elif d == 'p':
            s = 'AM' if tm.tm_hour < 12 else 'PM'
        elif d == 'P':
            s = 'am' if tm.tm_hour < 12 else 'pm'
        elif d == 'Z':
            s = zname
        elif d == 'z':
            a = abs(off)
            s = ('-' if off < 0 else '+') + '%02d%s%02d' % (a // 3600, ':' if colon else '',
                                                           a % 3600 // 60)
        elif d == 'u':
            s = str(tm.tm_wday + 1)
        elif d == 'w':
            s = str(wd_sun)
        elif d == 'U':
            s = num((tm.tm_yday + 6 - wd_sun) // 7, 2)
        elif d == 'W':
            s = num((tm.tm_yday + 6 - tm.tm_wday) // 7, 2)
        elif d in 'VGg':
            iso = datetime.date(tm.tm_year, tm.tm_mon, tm.tm_mday).isocalendar()
            s = num(iso[1], 2) if d == 'V' else (num(iso[0], 4) if d == 'G'
                                                 else num(iso[0] % 100, 2))
        elif d == 'F':
            s = '%04d-%02d-%02d' % (tm.tm_year, tm.tm_mon, tm.tm_mday)
        elif d == 'T' or d == 'X':
            s = '%02d:%02d:%02d' % (tm.tm_hour, tm.tm_min, tm.tm_sec)
        elif d == 'D' or d == 'x':
            s = '%02d/%02d/%02d' % (tm.tm_mon, tm.tm_mday, tm.tm_year % 100)
        elif d == 'R':
            s = '%02d:%02d' % (tm.tm_hour, tm.tm_min)
        elif d == 'r':
            s = '%02d:%02d:%02d %s' % (h12, tm.tm_min, tm.tm_sec,
                                       'AM' if tm.tm_hour < 12 else 'PM')
        elif d == 'c':
            s = '%s %s %2d %02d:%02d:%02d %d' % (_DAYS[tm.tm_wday][:3],
                                                 _MONTHS[tm.tm_mon - 1][:3], tm.tm_mday,
                                                 tm.tm_hour, tm.tm_min, tm.tm_sec, tm.tm_year)
        elif d == 'n':
            s = '\n'
        elif d == 't':
            s = '\t'
        elif d == '%':
            s = '%'
        else:
            s = '%' + flag + width + d
        if flag == '^':
            s = s.upper()
        out.append(s)
    return ''.join(out)
