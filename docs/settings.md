# Settings

All settings are optional. The [system checks](#system-checks) report values
django-mail-preview can't use when you run `manage.py check` or start the server.

## `MAIL_PREVIEW_STORAGE`

Default: `"files"`

Where captured messages are kept: `"files"` for the file storage, or the dotted path
of a `BaseStorage` subclass. See [Your own storage](inbox.md#your-own-storage).

## `MAIL_PREVIEW_ROOT`

Default: a directory under the system temp dir, named after a hash of `BASE_DIR`

The directory of the file storage, as a `str` or `Path`. It's created on first write.
Set it when two processes need to share one inbox, for example containers with their
own `/tmp`, or when you want the mail somewhere you can find it:

```python
MAIL_PREVIEW_ROOT = BASE_DIR / "mail-preview"
```

Keep that directory out of version control.

## `MAIL_PREVIEW_MAX_MESSAGES`

Default: `100`

How many captured messages to keep. After every send, the oldest messages beyond this
number are deleted. It must be an integer of 1 or more.

## `MAIL_PREVIEW_ALLOW`

Default: `None`

Dotted path of a function that takes the request and returns whether it may open the
pages. With the default, the pages open only while `DEBUG` is `True`. Setting it
replaces that rule entirely, so a staging server with `DEBUG = False` can show the
inbox to staff:

```python
MAIL_PREVIEW_ALLOW = "myproject.utils.mail_preview_allowed"
```

```python
def mail_preview_allowed(request):
    return request.user.is_staff
```

Every view calls it, the frame and the downloads included. See
[Security](security.md).

## System checks

| ID | Reports |
|---|---|
| `django_mail_preview.E001` | a `MAIL_PREVIEW_ALLOW` that can't be imported or isn't callable |
| `django_mail_preview.E002` | a `MAIL_PREVIEW_STORAGE` that isn't `"files"` or the path of an importable, concrete `BaseStorage` subclass |
| `django_mail_preview.E003` | a `MAIL_PREVIEW_MAX_MESSAGES` that isn't an integer of 1 or more |
| `django_mail_preview.E004` | a `MAIL_PREVIEW_ROOT` that isn't a `str` or `os.PathLike` |
| `django_mail_preview.W001` | the capture backend active while `DEBUG` is `False`, so mail is captured, not delivered |
| `django_mail_preview.W002` | a `MAIL_PREVIEW_*` setting django-mail-preview doesn't know, usually a typo, with the closest name as a hint |
| `django_mail_preview.W003` | the capture backend active without the URLs included, so captured mail can't be seen |

The checks never touch the disk. The storage directory is created on first write.
