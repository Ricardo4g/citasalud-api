import unittest

from main import Usuario, UsuarioRead


class UserSerializationTests(unittest.TestCase):
    def test_usuario_read_accepts_patient_email_with_local_domain(self) -> None:
        paciente = Usuario(
            nombre="Juan Pérez",
            correo="paciente_123@citasalud.local",
            contrasena_hash="hashed",
            rol="paciente",
            especialidad="",
            telefono="1234567890",
        )

        usuario_leido = UsuarioRead.model_validate(paciente)

        self.assertEqual(usuario_leido.correo, paciente.correo)


if __name__ == "__main__":
    unittest.main()
