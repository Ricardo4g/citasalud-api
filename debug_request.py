import requests
import traceback

try:
    r = requests.post('http://127.0.0.1:8001/operarios/register', json={'nombre':'Verify Operario','correo':'verifyoperario@example.com','contrasena':'123456','telefono':'123'})
    print('STATUS', r.status_code)
    print('TEXT', r.text)
    print('JSON', None)
    try:
        print('PARSED', r.json())
    except Exception:
        pass
except Exception:
    traceback.print_exc()
