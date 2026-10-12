"""Admin member profiles use native users, membership and reserved settings."""
import base64
import io
import re
from PIL import Image, ImageOps
from ledger import uuid
from setup_native import text


def email(value):
    value = text(value or '', 'Email').lower()
    if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ValueError('Enter a valid email address, or leave it blank')
    return value


def member_name(value):
    if not isinstance(value, str):
        raise ValueError('Name is missing or too long')
    value = value.strip()
    if not value:
        raise ValueError('Name is missing or too long')
    try:
        if len(value.encode('utf-8')) > 255:
            raise ValueError('Name is too long. Try a shorter name.')
    except UnicodeEncodeError:
        raise ValueError('Name is too long. Try a shorter name.') from None
    return value


def reject_future_credentials(data):
    if data.get('password') is not None or data.get('pin') is not None:
        raise ValueError('Password and PIN sign-in for badge-only people is planned for later. Refresh the user form.')


def creation_input(data):
    reject_future_credentials(data)
    return {'requestKey': uuid(data.get('request_key')), 'name': member_name(data.get('name', '')), 'email': email(data.get('email'))}


def avatar(value):
    if value == '':
        return ''
    if not isinstance(value, str) or len(value) > 55000:
        raise ValueError('Choose a smaller profile picture')
    prefix, separator, encoded = value.partition(',')
    if not separator or prefix not in ('data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'):
        raise ValueError('Choose a PNG, JPEG or WebP picture')
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in ('JPEG', 'PNG', 'WEBP') or picture.width > 256 or picture.height > 256:
                raise ValueError('Resize the profile picture to 256 pixels or smaller')
            picture.load()
            if picture.format == 'JPEG' and max(picture.size) <= 128 and len(raw) <= 40000 and not picture.getexif():
                return value
            picture = ImageOps.exif_transpose(picture).convert('RGBA')
            picture.thumbnail((128, 128))
            background = Image.new('RGB', picture.size, '#ffffff')
            background.paste(picture, mask=picture.getchannel('A'))
            output = io.BytesIO(); background.save(output, 'JPEG', quality=85)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValueError('Could not read this profile picture') from None
    return 'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode()


def profile_input(data):
    reject_future_credentials(data)
    notes = data.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 1000:
        raise ValueError('Keep notes under 1000 characters')
    version = data.get('updatedAt')
    if not isinstance(version, str) or not version or len(version) > 64:
        raise ValueError('Reload the profile before saving')
    return {'name': member_name(data.get('name', '')), 'email': email(data.get('email')), 'avatar': avatar(data.get('avatar', '')), 'notes': notes, 'updatedAt': version}


def create_account(client, data):
    return client.call('/api/v1/groups/members', 'POST', creation_input(data))


def get_profile(client, user_id):
    return client.call('/api/v1/groups/members/'+uuid(user_id)+'/profile')


def update_profile(client, user_id, data):
    return client.call('/api/v1/groups/members/'+uuid(user_id)+'/profile', 'PUT', profile_input(data))
