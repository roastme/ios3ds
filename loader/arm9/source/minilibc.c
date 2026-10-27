// Minimal freestanding libc for the loader (no newlib in this toolchain).
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

void *memset(void *d, int c, size_t n)
{
	unsigned char *p = d;
	while (n--)
		*p++ = (unsigned char)c;
	return d;
}

void *memcpy(void *d, const void *s, size_t n)
{
	unsigned char *dp = d;
	const unsigned char *sp = s;
	while (n--)
		*dp++ = *sp++;
	return d;
}

void *memmove(void *d, const void *s, size_t n)
{
	unsigned char *dp = d;
	const unsigned char *sp = s;
	if (dp < sp)
		return memcpy(d, s, n);
	while (n--)
		dp[n] = sp[n];
	return d;
}

int memcmp(const void *a, const void *b, size_t n)
{
	const unsigned char *x = a, *y = b;
	for (; n; n--, x++, y++)
		if (*x != *y)
			return *x - *y;
	return 0;
}

size_t strlen(const char *s)
{
	size_t n = 0;
	while (s[n])
		n++;
	return n;
}

char *strchr(const char *s, int c)
{
	for (; *s; s++)
		if (*s == (char)c)
			return (char *)s;
	return c ? NULL : (char *)s;
}

int strcmp(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return (unsigned char)*a - (unsigned char)*b;
}

int strncmp(const char *a, const char *b, size_t n)
{
	for (; n; n--, a++, b++)
		if (*a != *b || !*a)
			return (unsigned char)*a - (unsigned char)*b;
	return 0;
}

char *strcpy(char *d, const char *s)
{
	char *r = d;
	while ((*d++ = *s++))
		;
	return r;
}

char *strncpy(char *d, const char *s, size_t n)
{
	char *r = d;
	for (; n && *s; n--)
		*d++ = *s++;
	while (n--)
		*d++ = 0;
	return r;
}

int toupper(int c) { return (c >= 'a' && c <= 'z') ? c - 32 : c; }
int tolower(int c) { return (c >= 'A' && c <= 'Z') ? c + 32 : c; }

static void put(char *buf, size_t size, size_t *pos, char c)
{
	if (*pos + 1 < size)
		buf[*pos] = c;
	(*pos)++;
}

int vsnprintf(char *buf, size_t size, const char *fmt, va_list ap)
{
	size_t pos = 0;

	for (; *fmt; fmt++) {
		char tmp[12], pad = ' ';
		int width = 0, neg = 0, len = 0, base = 10, upper = 0, left = 0, prec = -1;
		const char *s;
		uint32_t u;

		if (*fmt != '%') {
			put(buf, size, &pos, *fmt);
			continue;
		}
		fmt++;
		if (*fmt == '-')
			left = 1, fmt++;
		if (*fmt == '0')
			pad = '0', fmt++;
		if (*fmt == '*') {
			width = va_arg(ap, int);
			fmt++;
		} else {
			while (*fmt >= '0' && *fmt <= '9')
				width = width * 10 + *fmt++ - '0';
		}
		if (*fmt == '.') {
			fmt++;
			prec = 0;
			if (*fmt == '*') {
				prec = va_arg(ap, int);
				fmt++;
			} else {
				while (*fmt >= '0' && *fmt <= '9')
					prec = prec * 10 + *fmt++ - '0';
			}
		}
		while (*fmt == 'l' || *fmt == 'z' || *fmt == 'h')
			fmt++;
		switch (*fmt) {
		case 's':
			s = va_arg(ap, const char *);
			if (!s)
				s = "(null)";
			len = strlen(s);
			if (prec >= 0 && len > prec)
				len = prec;
			for (; !left && len < width; width--)
				put(buf, size, &pos, ' ');
			for (int i = 0; i < len; i++)
				put(buf, size, &pos, s[i]);
			for (; left && len < width; width--)
				put(buf, size, &pos, ' ');
			continue;
		case 'c':
			put(buf, size, &pos, (char)va_arg(ap, int));
			continue;
		case 'd':
		case 'i': {
			int v = va_arg(ap, int);
			if (v < 0)
				neg = 1, u = -(uint32_t)v;
			else
				u = v;
			break;
		}
		case 'X':
			upper = 1;
			/* fall through */
		case 'x':
		case 'p':
			base = 16;
			/* fall through */
		case 'u':
			u = va_arg(ap, uint32_t);
			break;
		default:
			put(buf, size, &pos, *fmt);
			continue;
		}
		do {
			int d = u % base;
			tmp[len++] = d < 10 ? '0' + d : (upper ? 'A' : 'a') + d - 10;
			u /= base;
		} while (u);
		if (neg && pad == '0')
			put(buf, size, &pos, '-');
		for (width -= len + neg; width > 0; width--)
			put(buf, size, &pos, pad);
		if (neg && pad != '0')
			put(buf, size, &pos, '-');
		while (len)
			put(buf, size, &pos, tmp[--len]);
	}
	if (size)
		buf[pos < size ? pos : size - 1] = 0;
	return pos;
}

int snprintf(char *buf, size_t size, const char *fmt, ...)
{
	va_list ap;
	int r;
	va_start(ap, fmt);
	r = vsnprintf(buf, size, fmt, ap);
	va_end(ap);
	return r;
}

int sprintf(char *buf, const char *fmt, ...)
{
	va_list ap;
	int r;
	va_start(ap, fmt);
	r = vsnprintf(buf, 0x10000, fmt, ap);
	va_end(ap);
	return r;
}

size_t strnlen(const char *s, size_t max)
{
	size_t n = 0;
	while (n < max && s[n])
		n++;
	return n;
}

char *strtok(char *s, const char *delim)
{
	static char *next;
	char *tok;

	if (!s)
		s = next;
	if (!s)
		return NULL;
	while (*s && strchr(delim, *s))
		s++;
	if (!*s)
		return next = NULL;
	tok = s;
	while (*s && !strchr(delim, *s))
		s++;
	if (*s)
		*s++ = 0;
	next = s;
	return tok;
}

/* libgcc's division-by-zero handler calls raise() */
int raise(int sig)
{
	(void)sig;
	return 0;
}
