"""textkit: small text operations, served to customers one call at a time.

Every operation takes one string. The service calls ``getattr(textkit, op)(text)``; an operation
that is not here is one customers cannot use yet."""


def _words(text):
    return text.split()


def upper(text):
    return text.upper()


def lower(text):
    return text.lower()


def word_count(text):
    return len(text.split(" "))


def slugify(text):
    return text.lower().strip().replace(" ", "-")


def title_case(text):
    return " ".join(w.capitalize() for w in _words(text))


def reverse_words(text):
    return " ".join(reversed(_words(text)))
