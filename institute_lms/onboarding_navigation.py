"""Navigation hints from approved registration data; never access grants."""
import json


def teaching_path(rows, user):
    for row in rows:
        try:
            details = json.loads(row.get('details') or '{}')
        except (ValueError, TypeError):
            continue
        if not isinstance(details, dict):
            continue
        if (details.get('flow') in ('public-account-v1', 'provider-application-v1')
                and details.get('email') == user
                and details.get('kind') == 'Individual Teacher'
                and details.get('teaching_path') in ('individual', 'institute')):
            return details['teaching_path']
    return ''


def profile_pending(rows):
    for row in rows:
        try: details=json.loads(row.get('details') or '{}')
        except (ValueError,TypeError): continue
        if isinstance(details,dict) and details.get('flow')=='public-account-v1' and details.get('onboarding_version')==2:
            return details.get('onboarding_profile_completed') is not True
    return False


def workspace_registration(rows, user, kind):
    """Only a completed, matching registration can create an owned workspace."""
    expected = 'Institute' if kind == 'Institute' else 'Individual Teacher'
    for row in rows:
        try:
            details = json.loads(row.get('details') or '{}')
        except (ValueError, TypeError):
            continue
        if not isinstance(details, dict):
            continue
        if (details.get('flow') != 'public-account-v1'
                or details.get('email') != user or details.get('kind') != expected):
            continue
        if details.get('onboarding_version') == 2 and details.get('onboarding_profile_completed') is not True:
            return False
        return kind == 'Institute' or (kind == 'Teacher' and details.get('teaching_path') == 'individual')
    return False
