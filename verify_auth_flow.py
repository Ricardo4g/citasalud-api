import requests

base = 'http://127.0.0.1:8001'
email = 'verifyoperario@example.com'
payload = {'nombre': 'Verify Operario', 'correo': email, 'contrasena': '123456', 'telefono': '123'}

def try_register():
    r = requests.post(f"{base}/operarios/register", json=payload)
    if r.status_code == 201 or r.status_code == 200:
        return r.json().get('access_token')
    # If already registered, try to login
    try:
        body = r.json()
        if isinstance(body, dict) and body.get('detail') and 'registrado' in str(body.get('detail')):
            return try_login()
    except Exception:
        pass
    print('REGISTER_FAILED', r.status_code, r.text)
    return None

def try_login():
    r = requests.post(f"{base}/login", json={'correo': email, 'contrasena': payload['contrasena']})
    if r.status_code == 200:
        return r.json().get('access_token')
    print('LOGIN_FAILED', r.status_code, r.text)
    return None

token = try_register()
print('TOKEN_OK', bool(token))
if not token:
    raise SystemExit(1)

headers = {'Authorization': f'Bearer {token}'}
me = requests.get(f"{base}/operario/me", headers=headers)
print('ME_OK', me.json().get('correo') if me.ok else me.status_code)
users = requests.get(f"{base}/usuarios", headers=headers)
print('USERS_OK', len(users.json()) if users.ok else users.status_code)
