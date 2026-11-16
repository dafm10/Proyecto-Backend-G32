import secrets
from django.db import models
from django.utils import timezone
from uuid import uuid4
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager

class ManejadorUsuario(BaseUserManager):
    def create_superuser(self, nombre, correo, password):
        if not correo or len(correo) == 0:
            raise ValueError("El correo es obligatorio")

        correoNormalizado = self.normalize_email(correo)
        nuevoUsuario = self.model(correo = correoNormalizado, nombre = nombre)

        nuevoUsuario.set_password(password)
        nuevoUsuario.is_superuser = True
        nuevoUsuario.is_staff = True

        nuevoUsuario.save()
        # return nuevoUsuario

class Sede(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    nombre = models.CharField(max_length=100, null=False)
    direccion = models.TextField()
    telefono = models.CharField(max_length=20, blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "sedes"


class Usuario(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid4)
    nombre = models.TextField()
    apellido = models.TextField(null=True)
    sexo = models.TextField()
    correo = models.EmailField(max_length=254, unique=True)
    password = models.CharField(max_length=128)
    telefono = models.CharField(max_length=20, blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_column='activo')

    USERNAME_FIELD = 'correo'
    REQUIRED_FIELDS = ['nombre']

    objects = ManejadorUsuario()

    class Meta:
        db_table = "usuarios"


class Barbero(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    activo = models.BooleanField(default=True)
    sede = models.ForeignKey(to=Sede, on_delete=models.PROTECT, db_column='sede_id')
    usuario = models.OneToOneField(to=Usuario, on_delete=models.PROTECT, db_column='usuario_id', related_name='barbero')

    class Meta:
        db_table = "barberos"

class Cliente(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    usuario = models.OneToOneField(to=Usuario, on_delete=models.PROTECT, db_column='usuario_id', related_name='cliente')
    fecha_nacimiento = models.DateField(null=True, blank=True)

    @property
    def edad(self):
        if self.fecha_nacimiento is None:
            return None
        hoy = timezone.localdate()

        edad = hoy.year - self.fecha_nacimiento.year

        aun_no_cumple = (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)

        if aun_no_cumple:
            edad -= 1

        return edad

    class Meta:
        db_table = "clientes"


class Servicio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    nombre = models.CharField(max_length=100, null=False)
    descripcion = models.CharField(max_length=300, null=True)
    duracion = models.PositiveBigIntegerField()
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "servicios"


class ServicioSede(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    disponible = models.BooleanField(default=True)
    sede = models.ForeignKey(to=Sede, on_delete=models.PROTECT, db_column='sede_id')
    servicio = models.ForeignKey(to=Servicio, on_delete=models.PROTECT, db_column='servicio_id')

    class Meta:
        db_table = 'servicios_sedes'
        constraints = [
            models.UniqueConstraint(
                fields=["sede", "servicio"],
                name = "unique_servicio_sede"
            )
        ]

class BarberoServicio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    barbero = models.ForeignKey(to=Barbero, on_delete=models.PROTECT, db_column='barbero_id')
    servicio = models.ForeignKey(to=Servicio, on_delete=models.PROTECT, db_column='servicio_id')

    class Meta:
        db_table = 'barberos_servicios'
        constraints = [
            models.UniqueConstraint(
                fields=['barbero', 'servicio'],
                name='unique_barbero_servicio'
            )
        ]

class HorarioBarbero(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid4)

    barbero = models.ForeignKey(to=Barbero, on_delete=models.PROTECT, db_column='barbero_id')

    dia_semana = models.PositiveSmallIntegerField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        db_table = 'horarios_barberos'
        constraints = [
            models.UniqueConstraint(
                fields=['barbero', 'dia_semana', 'hora_inicio', 'hora_fin'],
                name='unique_horario_barbero'
            )
        ]


class BloqueAgenda(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    barbero = models.ForeignKey(to=Barbero, on_delete=models.PROTECT, db_column='barbero_id')
    fecha_hora_inicio = models.DateTimeField()
    fecha_hora_fin = models.DateTimeField()
    motivo = models.TextField(blank=True)

    class Meta:
        db_table = 'bloqueo_agenda'


def generar_codigo_cita():
    caracteres = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    codigo = ''

    for _ in range(7):
        caracter = secrets.choice(caracteres)
        codigo = codigo + caracter

    return codigo

class Cita(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
        ('pendiente_reprogramacion', 'Pendiente de aceptar reprogramación'),
        ('completada', 'Completada'),
        ('no_asistio', 'No asistió'),
        ('cancelada', 'Cancelada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4)
    codigo_cita = models.CharField(max_length=100, unique=True, default=generar_codigo_cita, editable=False)
    
    sede = models.ForeignKey(to=Sede, on_delete=models.PROTECT, db_column='sede_id')
    barbero = models.ForeignKey(to=Barbero, on_delete=models.PROTECT, db_column='barbero_id')
    servicio = models.ForeignKey(to=Servicio, on_delete=models.PROTECT, db_column='servicio_id')
    cliente = models.ForeignKey(to=Cliente, on_delete=models.PROTECT, db_column='cliente_id', null=True, blank=True)

    nombre_contacto = models.CharField(max_length=150)
    email_contacto = models.EmailField(max_length=254)
    telefono_contacto = models.CharField(max_length=9)

    fecha_hora_inicio = models.DateTimeField()
    fecha_hora_fin = models.DateTimeField()

    precio = models.DecimalField(max_digits=10, decimal_places=2)
    notas = models.TextField(blank=True)

    estado = models.CharField(max_length=40, choices=ESTADOS, default='pendiente')

    fecha_hora_registro = models.DateTimeField(auto_now_add=True)
    fecha_hora_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'citas'


class HistorialCita(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    cita = models.ForeignKey(to=Cita, on_delete=models.PROTECT, db_column='cita_id')
    accion = models.CharField(max_length=100)
    estado_previo = models.CharField(max_length=40, null=True, blank=True)
    estado_nuevo = models.CharField(max_length=40)
    inicio_anterior = models.DateTimeField(null=True, blank=True)
    fin_anterior = models.DateTimeField(null=True, blank=True)
    inicio_cita = models.DateTimeField()
    fin_cita = models.DateTimeField()

    modificado_por = models.ForeignKey(to=Usuario, on_delete=models.PROTECT, db_column='modificado_por_id', null=True, blank=True)

    tipo_acto = models.CharField(max_length=30)
    razon = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'historial_cita'