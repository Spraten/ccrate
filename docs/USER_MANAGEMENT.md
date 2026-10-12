# Manage users

Open **Collection → Members → Manage users → New user** in CACI-Create, or
**Admin → Manage users → New user** in Equipment Terminal. Only a name is
required. Email is optional contact information for a new badge-only person;
there is no required password or PIN. New people receive a stable native user
UUID and a generated avatar. Create and print a revocable badge using the
existing badge actions after creating the person.

Manage profile changes the name, optional email, other details and picture.
Upload a JPEG, PNG or WebP, or reset to the generated avatar. Uploaded pictures
are stored locally, reduced to a small JPEG, and stripped of upload metadata.
Both interfaces display the same saved picture. Names may repeat: use the
visible short user ID to distinguish people. Renaming preserves badges,
checkout history and the user UUID. Reprinting a badge updates its printed
name; its existing QR remains valid until explicitly revoked or replaced.

The native database remains the account authority. Badge-only users have a
NULL native password and ordinary member privileges. A private, unique
invalid-domain address satisfies the database's required email field; it is
not shown as personal contact information. No registration email is sent.
Existing web accounts keep their sign-in behavior. Collection owners can
manage profiles in a person's primary collection; shared collection profiles
are read-only and private notes are withheld. Workshop Admin's sign-in email
and owner access are protected. Native administration also retains configured
Workshop manager authorization. The Terminal retains its previously
approved temporary setup-admin access.

Removing collection membership retains the native user record and identity.
Revoke a badge to end badge access without deleting a person or their history.
A lost create or save response enters **Recovery**: inspect the actual saved
profile and resolve it explicitly. Creation uses the native user ID as a stable
request identity; profile recovery compares a digest of saved details. Recovery
journals retain identifiers and hashes, not uploaded pictures or private notes.
Uncertain writes and prints are never automatically repeated.

## Optional authentication later

Password and PIN enforcement are deliberately disabled. Unsupported credential
fields are rejected. The foundation is the existing native user UUID,
password-free account mode and separate revocable badge credential, rather
than a second user directory or speculative authentication tables.

A future optional web password should upgrade the same native person using
Homebox's password hashing and session mechanisms. Provide a unique login
handle or user ID so that a personal email remains optional. Credential changes
must preserve profile pictures, badges, loans and history.

Future QR-plus-PIN verification should first validate the current badge and
collection membership, then verify a separately hashed PIN in private credential
storage. Never use a PIN as the web password, place it in public profile settings,
or log its plaintext. Add rate limiting/backoff, audited administrator resets,
revocation and session invalidation, and bind challenges to the current person
and collection. This requires implementation and isolation tests before it is
enabled; no current badge scan requires a PIN.
