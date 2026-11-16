from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APITestCase
from .models import (
    Usuario, Sede, Barbero, Cliente, Servicio, ServicioSede,
    BarberoServicio, HorarioBarbero, Cita, HistorialCita,
)


class AccesoReservasTests(APITestCase):
    def setUp(self):
        self.admin = self.usuario('admin', is_staff=True)
        self.cliente = Cliente.objects.create(usuario=self.usuario('cliente'))
        self.otro = Cliente.objects.create(usuario=self.usuario('otro'))
        self.sede = Sede.objects.create(nombre='Centro', direccion='Dirección de prueba')
        self.barbero = Barbero.objects.create(usuario=self.usuario('barbero'), sede=self.sede)
        self.segundo = Barbero.objects.create(usuario=self.usuario('segundo'), sede=self.sede)
        self.servicio = Servicio.objects.create(nombre='Corte', duracion=30)
        ServicioSede.objects.create(sede=self.sede, servicio=self.servicio, precio=35)
        BarberoServicio.objects.create(barbero=self.barbero, servicio=self.servicio)
        self.inicio = (timezone.now() + timedelta(days=5)).replace(hour=15, minute=0, second=0, microsecond=0)
        for dia in range(7):
            HorarioBarbero.objects.create(barbero=self.barbero, dia_semana=dia, hora_inicio='00:00', hora_fin='23:59')
        self.cita = self.reservar(self.cliente, self.barbero)
        self.ajena = self.reservar(self.otro, self.segundo)

    def usuario(self, nombre, **opciones):
        usuario = Usuario(nombre=nombre, correo=f'{nombre}@example.com', telefono='987654321', sexo='M', **opciones)
        usuario.set_password('solo-para-pruebas')
        usuario.save()
        return usuario

    def reservar(self, cliente, barbero):
        return Cita.objects.create(
            sede=self.sede, barbero=barbero, servicio=self.servicio, cliente=cliente,
            nombre_contacto=cliente.usuario.nombre, email_contacto=cliente.usuario.correo,
            telefono_contacto='987654321', fecha_hora_inicio=self.inicio,
            fecha_hora_fin=self.inicio + timedelta(minutes=30), precio=35,
        )

    def test_catalogo_publico_y_citas_privadas(self):
        for ruta in ['/servicios', '/sedes', '/servicios-sedes', '/barberos']:
            self.assertEqual(self.client.get(ruta).status_code, 200)
        self.assertEqual(self.client.get('/citas').status_code, 401)
        self.assertEqual(self.client.post('/sedes', {}, format='json').status_code, 401)

    def test_login_y_perfil_de_los_tres_roles(self):
        for usuario, rol in [(self.admin, 'administrador'), (self.cliente.usuario, 'cliente'), (self.barbero.usuario, 'barbero')]:
            respuesta = self.client.post('/login', {'correo': usuario.correo, 'password': 'solo-para-pruebas'}, format='json')
            self.assertEqual(respuesta.status_code, 200)
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
            self.assertEqual(self.client.get('/perfil').data['rol'], rol)
        self.client.credentials()

    def test_listado_y_objetos_limitados_al_usuario(self):
        for usuario in [self.cliente.usuario, self.barbero.usuario]:
            self.client.force_authenticate(usuario)
            respuesta = self.client.get('/citas')
            self.assertEqual([item['id'] for item in respuesta.data['content']], [str(self.cita.id)])
            self.assertEqual(self.client.get(f'/cita/{self.ajena.id}').status_code, 404)
            self.assertEqual(self.client.get(f'/cita/{self.ajena.id}/historial').status_code, 404)
            self.assertEqual(self.client.get(f'/cita/{self.cita.id}/historial').status_code, 200)
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.client.get('/citas').data['content']), 2)

    def test_cliente_no_puede_modificar_citas_ajenas_ni_confirmar(self):
        self.client.force_authenticate(self.cliente.usuario)
        self.assertEqual(self.client.patch(f'/cita/{self.ajena.id}/cancelar', {}, format='json').status_code, 404)
        self.assertEqual(self.client.patch(f'/cita/{self.ajena.id}/reprogramar', {'fecha_hora_inicio': self.inicio.isoformat()}, format='json').status_code, 404)
        self.assertEqual(self.client.patch(f'/cita/{self.cita.id}/confirmar', {}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/cita/{self.cita.id}/completar', {}, format='json').status_code, 403)

    def test_cancelacion_propia_registra_actor_cliente(self):
        self.client.force_authenticate(self.cliente.usuario)
        self.assertEqual(self.client.patch(f'/cita/{self.cita.id}/cancelar', {}, format='json').status_code, 200)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'cancelada')
        self.assertEqual(HistorialCita.objects.get(cita=self.cita).tipo_acto, 'cliente')

    def test_barbero_solo_consulta_sus_citas(self):
        self.client.force_authenticate(self.barbero.usuario)
        self.assertEqual(self.client.post('/citas', {}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/cita/{self.cita.id}/cancelar', {}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/cita/{self.cita.id}/reprogramar', {}, format='json').status_code, 403)

    def test_reserva_asigna_cliente_autenticado_aunque_envie_otro(self):
        self.client.force_authenticate(self.cliente.usuario)
        respuesta = self.client.post('/citas', {
            'sede': str(self.sede.id), 'barbero': str(self.barbero.id),
            'servicio': str(self.servicio.id), 'cliente': str(self.otro.id),
            'nombre_contacto': 'Otra persona',
            'fecha_hora_inicio': (self.inicio + timedelta(hours=1)).isoformat(),
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        cita = Cita.objects.get(id=respuesta.data['content']['id'])
        self.assertEqual(cita.cliente_id, self.cliente.id)
        self.assertEqual(cita.nombre_contacto, self.cliente.usuario.nombre)

    def test_disponibilidad_publica_no_expone_datos_personales(self):
        respuesta = self.client.get('/disponibilidad', {
            'sede': self.sede.id, 'barbero': self.barbero.id,
            'servicio': self.servicio.id, 'fecha': self.inicio.date().isoformat(),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data['content'])
        for turno in respuesta.data['content']:
            self.assertEqual(set(turno), {'hora', 'disponible'})

    def test_registro_publico_crea_cuenta_y_permite_login_como_cliente(self):
        respuesta = self.client.post('/registro', {
            'nombre': 'Nueva cliente', 'correo': 'nueva@example.com',
            'telefono': '987654321', 'sexo': 'F', 'password': 'clave-de-prueba',
            'is_staff': True,
        }, format='json')
        self.assertEqual(respuesta.status_code, 201)
        usuario = Usuario.objects.get(correo='nueva@example.com')
        self.assertTrue(usuario.check_password('clave-de-prueba'))
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        login = self.client.post('/login', {
            'correo': usuario.correo, 'password': 'clave-de-prueba',
        }, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")
        self.assertEqual(self.client.get('/perfil').data['rol'], 'cliente')

    def test_registro_rechaza_correo_duplicado(self):
        cantidad = Usuario.objects.count()
        respuesta = self.client.post('/registro', {
            'nombre': 'Duplicado', 'correo': self.cliente.usuario.correo,
            'telefono': '987654321', 'sexo': 'M', 'password': 'clave-de-prueba',
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('correo', respuesta.data['content'])
        self.assertEqual(Usuario.objects.count(), cantidad)

    def test_invitado_reserva_sin_cuenta_y_no_se_asocia_a_otro_cliente(self):
        usuarios = Usuario.objects.count()
        clientes = Cliente.objects.count()
        respuesta = self.client.post('/citas', {
            'sede': str(self.sede.id), 'barbero': str(self.barbero.id),
            'servicio': str(self.servicio.id), 'cliente': str(self.otro.id),
            'nombre_contacto': 'Invitada', 'email_contacto': 'invitada@example.com',
            'telefono_contacto': '987654321',
            'fecha_hora_inicio': (self.inicio + timedelta(hours=2)).isoformat(),
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        cita = Cita.objects.get(id=respuesta.data['content']['id'])
        self.assertIsNone(cita.cliente_id)
        self.assertEqual(cita.nombre_contacto, 'Invitada')
        evento = HistorialCita.objects.get(cita=cita)
        self.assertIsNone(evento.modificado_por_id)
        self.assertEqual(evento.tipo_acto, 'invitado')
        self.assertEqual(Usuario.objects.count(), usuarios)
        self.assertEqual(Cliente.objects.count(), clientes)
        self.assertEqual(self.client.get('/citas').status_code, 401)
        self.assertEqual(self.client.get(f'/cita/{cita.id}').status_code, 401)
        self.assertEqual(self.client.get(f'/cita/{cita.id}/historial').status_code, 401)

    def test_invitado_debe_enviar_sus_datos_de_contacto(self):
        cantidad = Cita.objects.count()
        respuesta = self.client.post('/citas', {
            'sede': str(self.sede.id), 'barbero': str(self.barbero.id),
            'servicio': str(self.servicio.id),
            'fecha_hora_inicio': (self.inicio + timedelta(hours=2)).isoformat(),
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('nombre_contacto', respuesta.data['content'])
        self.assertEqual(Cita.objects.count(), cantidad)

    def test_admin_registra_barbero_con_cuenta_sede_y_servicios(self):
        self.client.force_authenticate(self.admin)
        datos = {
            'cuenta': {
                'nombre': 'Nuevo barbero', 'correo': 'nuevo.barbero@example.com',
                'telefono': '987654321', 'sexo': 'M', 'password': 'clave-de-prueba',
            },
            'sede': str(self.sede.id), 'servicios': [str(self.servicio.id)],
        }
        respuesta = self.client.post('/registro-barbero', datos, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        usuario = Usuario.objects.get(correo='nuevo.barbero@example.com')
        self.assertTrue(usuario.check_password('clave-de-prueba'))
        self.assertFalse(usuario.is_staff)
        barbero = Barbero.objects.get(usuario=usuario)
        self.assertEqual(barbero.sede_id, self.sede.id)
        self.assertTrue(BarberoServicio.objects.filter(barbero=barbero, servicio=self.servicio).exists())
        self.client.force_authenticate(usuario)
        self.assertEqual(self.client.get('/perfil').data['rol'], 'barbero')
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post('/registro-barbero', datos, format='json').status_code, 400)
        self.assertEqual(Usuario.objects.filter(correo='nuevo.barbero@example.com').count(), 1)

    def test_alta_barbero_revierte_todo_si_falla_asignacion(self):
        from unittest.mock import patch
        from django.db import IntegrityError
        self.client.force_authenticate(self.admin)
        cantidad = Barbero.objects.count()
        with patch('gestion.serializers.BarberoServicio.objects.create', side_effect=IntegrityError):
            respuesta = self.client.post('/registro-barbero', {
                'cuenta': {
                    'nombre': 'Prueba rollback', 'correo': 'rollback@example.com',
                    'telefono': '987654321', 'sexo': 'M', 'password': 'clave-de-prueba',
                },
                'sede': str(self.sede.id), 'servicios': [str(self.servicio.id)],
            }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Usuario.objects.filter(correo='rollback@example.com').exists())
        self.assertEqual(Barbero.objects.count(), cantidad)

    def test_alta_barbero_con_usuario_existente_conserva_formato_original(self):
        usuario = self.usuario('sinperfil')
        self.client.force_authenticate(self.admin)
        respuesta = self.client.post('/registro-barbero', {
            'usuario': str(usuario.id), 'sede': str(self.sede.id),
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue(Barbero.objects.filter(usuario=usuario).exists())

    def test_solo_admin_puede_crear_sedes_y_barberos(self):
        for usuario in [self.cliente.usuario, self.barbero.usuario]:
            self.client.force_authenticate(usuario)
            self.assertEqual(self.client.post('/sedes', {}, format='json').status_code, 403)
            self.assertEqual(self.client.post('/registro-barbero', {}, format='json').status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post('/registro-barbero', {}, format='json').status_code, 401)

    def test_admin_crea_sede_y_configura_servicio_precio(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.post('/sedes', {
            'nombre': 'Nueva sede', 'direccion': 'Dirección nueva', 'telefono': '987654321',
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        sede = respuesta.data['content']['id']
        respuesta = self.client.post('/servicios-sedes', {
            'sede': sede, 'servicio': str(self.servicio.id), 'precio': '45.00', 'disponible': True,
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue(ServicioSede.objects.filter(sede_id=sede, servicio=self.servicio, precio=45).exists())

    def test_admin_edita_datos_de_sede(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.patch(f'/sede/{self.sede.id}', {
            'nombre': 'Centro renovado', 'direccion': 'Nueva dirección', 'telefono': '012345678',
        }, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.sede.refresh_from_db()
        self.assertEqual(self.sede.nombre, 'Centro renovado')
        self.assertEqual(self.sede.direccion, 'Nueva dirección')
        self.assertEqual(self.sede.telefono, '012345678')
        self.assertTrue(respuesta.data['content']['activo'])
        self.assertEqual(self.client.patch(f'/sede/{self.sede.id}', {'nombre': ''}, format='json').status_code, 400)

    def test_admin_desactiva_y_reactiva_sede_sin_exponer_inactivas(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(f'/sede/{self.sede.id}', {'activo': False}, format='json').status_code, 200)
        self.assertFalse(self.client.get(f'/sede/{self.sede.id}').data['content']['activo'])
        listado = self.client.get('/sedes?incluir_inactivas=true').data['content']
        self.assertEqual(listado[0]['id'], str(self.sede.id))
        self.assertFalse(listado[0]['activo'])
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/sedes?incluir_inactivas=true').data['content'], [])
        self.assertEqual(self.client.get(f'/sede/{self.sede.id}').status_code, 404)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(f'/sede/{self.sede.id}', {'activo': True}, format='json').status_code, 200)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f'/sede/{self.sede.id}').status_code, 200)

    def test_editar_sede_requiere_administrador(self):
        for usuario in [self.cliente.usuario, self.barbero.usuario]:
            self.client.force_authenticate(usuario)
            self.assertEqual(self.client.patch(f'/sede/{self.sede.id}', {'activo': False}, format='json').status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.patch(f'/sede/{self.sede.id}', {'nombre': 'Ajeno'}, format='json').status_code, 401)
        self.sede.refresh_from_db()
        self.assertTrue(self.sede.activo)
        self.assertEqual(self.sede.nombre, 'Centro')

    def test_admin_edita_cuenta_barbero_y_conserva_password(self):
        self.client.force_authenticate(self.admin)
        usuario = self.barbero.usuario
        hashAnterior = usuario.password
        respuesta = self.client.patch(f'/barbero/{self.barbero.id}', {
            'cuenta': {'nombre': 'Nombre actualizado', 'apellido': 'Apellido', 'correo': usuario.correo, 'telefono': '912345678'},
            'servicios': [str(self.servicio.id)],
        }, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        usuario.refresh_from_db()
        self.assertEqual(usuario.nombre, 'Nombre actualizado')
        self.assertEqual(usuario.apellido, 'Apellido')
        self.assertEqual(usuario.password, hashAnterior)
        self.assertNotIn('password', respuesta.data['content'])

    def test_edicion_barbero_no_afecta_asignaciones_con_citas_pendientes(self):
        self.client.force_authenticate(self.admin)
        otraSede = Sede.objects.create(nombre='Otra sede', direccion='Otra dirección')
        for cambios in [{'sede': str(otraSede.id)}, {'servicios': []}]:
            respuesta = self.client.patch(f'/barbero/{self.barbero.id}', {
                **cambios, 'cuenta': {'nombre': 'No debe guardarse'},
            }, format='json')
            self.assertEqual(respuesta.status_code, 400)
        self.barbero.refresh_from_db()
        self.barbero.usuario.refresh_from_db()
        self.assertEqual(self.barbero.sede_id, self.sede.id)
        self.assertEqual(self.barbero.usuario.nombre, 'barbero')
        self.assertTrue(BarberoServicio.objects.filter(barbero=self.barbero, servicio=self.servicio).exists())

    def test_admin_cambia_sede_y_servicios_sin_citas_pendientes(self):
        self.client.force_authenticate(self.admin)
        self.cita.estado = 'cancelada'
        self.cita.save(update_fields=['estado'])
        otraSede = Sede.objects.create(nombre='Otra sede', direccion='Otra dirección')
        otroServicio = Servicio.objects.create(nombre='Barba', duracion=20)
        respuesta = self.client.patch(f'/barbero/{self.barbero.id}', {
            'sede': str(otraSede.id), 'servicios': [str(otroServicio.id)],
        }, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.barbero.refresh_from_db()
        self.assertEqual(self.barbero.sede_id, otraSede.id)
        self.assertEqual(list(BarberoServicio.objects.filter(barbero=self.barbero).values_list('servicio_id', flat=True)), [otroServicio.id])

    def test_eliminar_barbero_es_reversible_y_conserva_citas(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f'/barbero/{self.barbero.id}').status_code, 204)
        self.barbero.refresh_from_db()
        self.assertFalse(self.barbero.activo)
        self.assertTrue(Cita.objects.filter(id=self.cita.id).exists())
        self.assertTrue(Usuario.objects.filter(id=self.barbero.usuario_id).exists())
        listado = self.client.get('/barberos?incluir_inactivos=true').data['content']
        self.assertTrue(any(item['id'] == str(self.barbero.id) and not item['activo'] for item in listado))
        self.assertEqual(self.client.patch(f'/barbero/{self.barbero.id}', {'activo': True}, format='json').status_code, 200)
        self.client.force_authenticate(user=None)
        for item in self.client.get('/barberos?incluir_inactivos=true').data['content']:
            self.assertNotIn('correo', item)
            self.assertNotIn('telefono', item)
        self.assertEqual(self.client.get(f'/barbero/{self.barbero.id}').status_code, 401)

    def test_editar_y_eliminar_barbero_solo_administrador(self):
        for usuario in [self.cliente.usuario, self.barbero.usuario]:
            self.client.force_authenticate(usuario)
            self.assertEqual(self.client.patch(f'/barbero/{self.barbero.id}', {}, format='json').status_code, 403)
            self.assertEqual(self.client.delete(f'/barbero/{self.barbero.id}').status_code, 403)
        self.barbero.refresh_from_db()
        self.assertTrue(self.barbero.activo)

    def test_correo_duplicado_no_modifica_barbero(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.patch(f'/barbero/{self.barbero.id}', {
            'cuenta': {'correo': self.cliente.usuario.correo, 'nombre': 'No guardar'}, 'activo': False,
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.barbero.refresh_from_db()
        self.barbero.usuario.refresh_from_db()
        self.assertTrue(self.barbero.activo)
        self.assertEqual(self.barbero.usuario.nombre, 'barbero')

    def test_apellido_vacio_es_valido_al_crear_y_editar_barbero(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.post('/registro-barbero', {
            'cuenta': {
                'nombre': 'Sin apellido', 'apellido': '', 'correo': 'sinapellido@example.com',
                'telefono': '987654321', 'sexo': 'M', 'password': 'clave-de-prueba',
            },
            'sede': str(self.sede.id), 'servicios': [str(self.servicio.id)],
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(Usuario.objects.get(correo='sinapellido@example.com').apellido, '')
        respuesta = self.client.patch(f'/barbero/{self.barbero.id}', {
            'cuenta': {'apellido': ''},
        }, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.barbero.usuario.refresh_from_db()
        self.assertEqual(self.barbero.usuario.apellido, '')

    def test_login_devuelve_errores_asociados_al_campo(self):
        respuesta = self.client.post('/login', {
            'correo': 'noexiste@example.com', 'password': 'clave-de-prueba',
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('correo', respuesta.data['content'])
        respuesta = self.client.post('/login', {
            'correo': self.cliente.usuario.correo, 'password': 'equivocada',
        }, format='json')
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('password', respuesta.data['content'])

    def test_alta_barbero_incluye_horarios_iniciales(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.post('/registro-barbero', {
            'cuenta': {'nombre': 'Con horario', 'correo': 'horario@example.com', 'telefono': '987654321', 'sexo': 'M', 'password': 'clave-de-prueba'},
            'sede': str(self.sede.id), 'servicios': [str(self.servicio.id)],
            'horarios': [
                {'dia_semana': 0, 'hora_inicio': '09:00', 'hora_fin': '13:00'},
                {'dia_semana': 0, 'hora_inicio': '14:00', 'hora_fin': '18:00'},
            ],
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(HorarioBarbero.objects.filter(barbero_id=respuesta.data['content']['id']).count(), 2)

    def test_alta_con_horarios_superpuestos_no_crea_cuenta(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.post('/registro-barbero', {
            'cuenta': {'nombre': 'Horario inválido', 'correo': 'invalido@example.com', 'telefono': '987654321', 'sexo': 'M', 'password': 'clave-de-prueba'},
            'sede': str(self.sede.id), 'servicios': [str(self.servicio.id)],
            'horarios': [
                {'dia_semana': 0, 'hora_inicio': '09:00', 'hora_fin': '13:00'},
                {'dia_semana': 0, 'hora_inicio': '12:00', 'hora_fin': '18:00'},
            ],
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('horarios', respuesta.data['content'])
        self.assertFalse(Usuario.objects.filter(correo='invalido@example.com').exists())

    def test_gestion_horario_protege_citas_existentes(self):
        from zoneinfo import ZoneInfo
        self.client.force_authenticate(self.admin)
        dia = timezone.localtime(self.inicio, ZoneInfo('America/Lima')).weekday()
        respuesta = self.client.post('/horarios-barberos', {
            'barbero': str(self.segundo.id), 'dia_semana': dia, 'hora_inicio': '09:00', 'hora_fin': '18:00',
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        id = respuesta.data['content']['id']
        self.assertEqual(self.client.patch(f'/horario-barbero/{id}', {'hora_fin': '19:00'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'/horario-barbero/{id}', {'hora_fin': '09:30'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'/horario-barbero/{id}').status_code, 400)
        self.ajena.estado = 'cancelada'
        self.ajena.save(update_fields=['estado'])
        self.assertEqual(self.client.delete(f'/horario-barbero/{id}').status_code, 204)

    def test_no_se_puede_transferir_un_horario_a_otro_barbero(self):
        self.client.force_authenticate(self.admin)
        horario = HorarioBarbero.objects.filter(barbero=self.barbero).first()
        respuesta = self.client.patch(f'/horario-barbero/{horario.id}', {'barbero': str(self.segundo.id)}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        horario.refresh_from_db()
        self.assertEqual(horario.barbero_id, self.barbero.id)

    def test_crear_editar_y_eliminar_bloqueo(self):
        self.client.force_authenticate(self.admin)
        inicio = self.inicio + timedelta(hours=1)
        fin = inicio + timedelta(hours=1)
        respuesta = self.client.post('/bloqueos-agenda', {
            'barbero': str(self.barbero.id), 'fecha_hora_inicio': inicio.isoformat(),
            'fecha_hora_fin': fin.isoformat(), 'motivo': 'Trámite',
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        id = respuesta.data['content']['id']
        self.assertIn('content', self.client.get(f'/bloqueo-agenda/{id}').data)
        respuesta = self.client.patch(f'/bloqueo-agenda/{id}', {'motivo': 'Ausencia'}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['content']['motivo'], 'Ausencia')
        self.assertEqual(self.client.delete(f'/bloqueo-agenda/{id}').status_code, 204)

    def test_bloqueo_no_puede_superponerse_a_una_cita(self):
        self.client.force_authenticate(self.admin)
        respuesta = self.client.post('/bloqueos-agenda', {
            'barbero': str(self.barbero.id), 'fecha_hora_inicio': self.inicio.isoformat(),
            'fecha_hora_fin': (self.inicio + timedelta(hours=1)).isoformat(),
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)

    def test_cliente_y_barbero_no_modifican_horarios(self):
        horario = HorarioBarbero.objects.filter(barbero=self.barbero).first()
        for usuario in [self.cliente.usuario, self.barbero.usuario]:
            self.client.force_authenticate(usuario)
            self.assertEqual(self.client.post('/horarios-barberos', {}, format='json').status_code, 403)
            self.assertEqual(self.client.patch(f'/horario-barbero/{horario.id}', {}, format='json').status_code, 403)
            self.assertEqual(self.client.delete(f'/horario-barbero/{horario.id}').status_code, 403)
            self.assertEqual(self.client.post('/bloqueos-agenda', {}, format='json').status_code, 403)

    def test_cliente_responde_solo_su_reprogramacion(self):
        self.cita.estado = 'pendiente_reprogramacion'
        self.cita.save(update_fields=['estado'])
        self.ajena.estado = 'pendiente_reprogramacion'
        self.ajena.save(update_fields=['estado'])
        self.client.force_authenticate(self.cliente.usuario)
        ruta = f'/cita/{self.cita.id}/responder-reprogramacion'
        self.assertEqual(self.client.patch(f'/cita/{self.ajena.id}/responder-reprogramacion', {'aceptada': True}, format='json').status_code, 404)
        respuesta = self.client.patch(ruta, {'aceptada': True}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'confirmada')
        self.assertEqual(HistorialCita.objects.get(cita=self.cita).accion, 'reprogramacion_aceptada')

    def test_admin_registra_respuesta_con_razon_y_rechazo_cancela(self):
        self.cita.estado = 'pendiente_reprogramacion'
        self.cita.save(update_fields=['estado'])
        self.client.force_authenticate(self.admin)
        ruta = f'/cita/{self.cita.id}/responder-reprogramacion'
        respuesta = self.client.patch(ruta, {'aceptada': False}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('razon', respuesta.data['content'])
        respuesta = self.client.patch(ruta, {'aceptada': False, 'razon': 'Cliente rechazó por teléfono'}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'cancelada')

    def test_ausencia_solo_admin_y_despues_del_horario(self):
        self.cita.estado = 'confirmada'
        self.cita.save(update_fields=['estado'])
        ruta = f'/cita/{self.cita.id}/no-asistio'
        for usuario in [self.cliente.usuario, self.barbero.usuario]:
            self.client.force_authenticate(usuario)
            self.assertEqual(self.client.patch(ruta, {}, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(ruta, {}, format='json').status_code, 400)
        self.cita.fecha_hora_inicio = timezone.now() - timedelta(hours=2)
        self.cita.fecha_hora_fin = timezone.now() - timedelta(hours=1)
        self.cita.save()
        respuesta = self.client.patch(ruta, {'razon': 'No llegó'}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'no_asistio')
        self.assertEqual(HistorialCita.objects.get(cita=self.cita).accion, 'no_asistio')

    def test_completar_cita_confirmada_finalizada(self):
        self.client.force_authenticate(self.admin)
        ruta = f'/cita/{self.cita.id}/completar'
        self.assertEqual(self.client.patch(ruta, {}, format='json').status_code, 400)
        self.cita.estado = 'confirmada'
        self.cita.fecha_hora_inicio = timezone.now() - timedelta(hours=2)
        self.cita.fecha_hora_fin = timezone.now() - timedelta(hours=1)
        self.cita.save()
        respuesta = self.client.patch(ruta, {}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'completada')
        self.assertEqual(HistorialCita.objects.get(cita=self.cita).accion, 'completada')
        self.assertEqual(self.client.patch(f'/cita/{self.cita.id}/no-asistio', {}, format='json').status_code, 400)
