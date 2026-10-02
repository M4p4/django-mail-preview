# Security

The pages show the content of every email your app sends, password-reset links
included, so who can open them matters.

## Who can open the pages

By default every view answers 404 unless `DEBUG` is `True`. To anyone else the URLs
don't exist, which is why the include can stay in `urlpatterns` unconditionally.

[`MAIL_PREVIEW_ALLOW`](settings.md#mail_preview_allow) replaces that rule with your
own, for a staging server that runs with `DEBUG = False`:

```python
MAIL_PREVIEW_ALLOW = "myproject.utils.mail_preview_allowed"
```

```python
def mail_preview_allowed(request):
    return request.user.is_staff
```

The function runs on every request to the pages, the frame and the downloads
included, and anything falsy is a 404. A function that returns `True` opens the inbox
to the world, so make it look at something about the request: the user, a header your
proxy sets, the client address.

## Email HTML in a sandbox

An email's HTML is served from its own URL into an `<iframe sandbox>` without
`allow-scripts` or `allow-same-origin`. The framed document has an opaque origin, so
it can read neither your cookies nor the page around it. Links open in a new tab
through an injected `<base target="_blank">`.

The frame's response carries a Content Security Policy that lets images, stylesheets
and fonts load from anywhere, as a mail client would, and nothing else:

```text
Content-Security-Policy: default-src 'none'; img-src data: http: https:;
    style-src 'unsafe-inline' http: https:; font-src data: http: https:;
    base-uri 'none'; frame-ancestors 'self';
    sandbox allow-popups allow-popups-to-escape-sandbox
X-Frame-Options: SAMEORIGIN
Referrer-Policy: no-referrer
```

Scripts never run, even when the HTML is opened in its own tab, because the policy's
`sandbox` directive applies to a plain navigation too. `base-uri 'none'` keeps an
email's own `<base>` from rewriting relative URLs, and `no-referrer` keeps the
message's URL out of the logs behind tracking pixels.

Remote images and stylesheets do load, as in a mail client, so a tracking pixel in a
captured message is requested when you open its HTML tab, though without a referrer.
A preview that hid remote images would show the email differently from a client.

Inline images, the `cid:` references, are embedded in the frame as `data:` URIs
rather than linked by their part URLs. The sandboxed document has no origin, so the
browser sends no cookie with the requests it makes, and a cookie-based
`MAIL_PREVIEW_ALLOW` would otherwise answer every inline image with a 404.

## Downloads

Parts and `.eml` files are served with `Content-Disposition: attachment`,
`X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox; default-src
'none'`, whatever their type. A stored SVG or HTML attachment is saved, never rendered
as a page in your site's origin, even when its URL is opened directly. Browsers ignore
`Content-Disposition` for `<img>` subresources, so inline images still render inside
the frame.

## Django's CSP middleware

On Django 6.0 and later, a project's `ContentSecurityPolicyMiddleware` leaves the
frame and the downloads alone, because those views override the project's policy and
report-only policy with their own. Without that, every inline style in every email
would land in your report endpoint. The other pages take the project's policy and
need no nonce, since they have no inline script, style or event handler attribute.

## Forms

Delete and "Clear all" are POST forms behind Django's CSRF check. The pages set the
CSRF cookie themselves, so the forms work whatever your middleware order.

## Production

The backend captures mail instead of delivering it, and captured mail is plain files,
readable by anyone with access to the directory. Keep the backend in development
settings. The system check `django_mail_preview.W001` warns when it's active while
`DEBUG` is `False`.
