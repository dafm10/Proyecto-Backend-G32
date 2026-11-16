from rest_framework.serializers import DateField, PrimaryKeyRelatedField, BooleanField, IntegerField, TimeField
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone
from rest_framework.serializers import ModelSerializer, Serializer, EmailField, CharField, ValidationError, SerializerMethodField, DateTimeField
from .models import Usuario, Sede, Barbero, Cliente, Servicio, ServicioSede, BarberoServicio, HorarioBarbero, BloqueAgenda, Cita, HistorialCita

class UsuarioSerializer(ModelSerializer):
    class Meta:
        model = Usuario
        exclude = ['is_staff', 'is_superuser', 'is_active', 'user_permissions', 'last_login', 'groups']

        extra_kwargs = {
            'password': {
                'write_only': True
            }
        }

class SedeSerializer(ModelSerializer):
    class Meta:
        model = Sede
        fields = "__all__"
        extra_kwargs = {
            "activo": {"write_only": True}
        }

class LoginSerializer(Serializer):
    correo = EmailField(required = True)
    password = CharField(required = True)


class SedeAdministracionSerializer(ModelSerializer):
    class Meta:
        model = Sede
        fields = '__all__'
        read_only_fields = ('id',)

class BarberoSerializer(ModelSerializer):
    class Meta:
        model = Barbero
        fields = '__all__'

class ClienteSerializer(ModelSerializer):
    class Meta:
        model = Cliente
        fields = '__all__'

class ServicioSerializer(ModelSerializer):
    class Meta:
        model = Servicio
        fields = '__all__'
        extra_kwargs = {
            'duracion': {'min_value': 1}
        }

class ServicioSedeSerializer(ModelSerializer):
    class Meta:
        model = ServicioSede
        fields = '__all__'

    def validate_sede(self, sede):
        if not sede.activo:
            raise ValidationError("La sede está inactiva")

        return sede

    def validate_servicio(self, servicio):
        if not servicio.activo:
            raise ValidationError("El servicio está inactivo")

        return servicio


class BarberoServicioSerializer(ModelSerializer):
    class Meta:
        model = BarberoServicio
        fields = '__all__'

    def validate_barbero(self, barbero):
        if not barbero.activo:
            raise ValidationError("El barbero está inactivo")

        if not barbero.usuario.is_active:
            raise ValidationError("El usuario del barbero está inactivo")

        return barbero

    def validate_servicio(self, servicio):
        if not servicio.activo:
            raise ValidationError("El servicio está inactivo")

        return servicio

def validarCoberturaHorarios(barbero, horarios):
    zona = ZoneInfo('America/Lima')
    citas = Cita.objects.filter(
        barbero=barbero, estado__in=['pendiente', 'confirmada', 'pendiente_reprogramacion'],
        fecha_hora_fin__gt=timezone.now()
    ).values_list('fecha_hora_inicio', 'fecha_hora_fin')
    for inicio, fin in citas:
        inicio = timezone.localtime(inicio, zona)
        fin = timezone.localtime(fin, zona)
        cubierto = inicio.date() == fin.date() and any(
            horario['dia_semana'] == inicio.weekday()
            and horario['hora_inicio'] <= inicio.time()
            and horario['hora_fin'] >= fin.time()
            for horario in horarios
        )
        if not cubierto:
            raise ValidationError('El cambio dejaría una cita pendiente fuera del horario. Reprograma o cancela esa cita primero')


class HorarioBarberoSerializer(ModelSerializer):
    dia_nombre = SerializerMethodField()

    class Meta:
        model = HorarioBarbero
        fields = '__all__'

    def get_dia_nombre(self, horario):
        dias = [
            'Lunes',
            'Martes',
            'Miércoles',
            'Jueves',
            'Viernes',
            'Sábado',
            'Domingo'
        ]

        return dias[horario.dia_semana]

    def validate_barbero(self, barbero):
        if not barbero.activo:
            raise ValidationError("El barbero está inactivo")

        return barbero

    def validate_dia_semana(self, dia_semana):
        if dia_semana < 0 or dia_semana > 6:
            raise ValidationError('El día debe estar entre 0 y 6')

        return dia_semana

    def validate(self, datos):
        if self.instance:
            barbero = datos.get('barbero', self.instance.barbero)
            dia = datos.get('dia_semana', self.instance.dia_semana)
            inicio = datos.get('hora_inicio', self.instance.hora_inicio)
            fin = datos.get('hora_fin', self.instance.hora_fin)
        else:
            barbero = datos.get('barbero')
            dia = datos.get('dia_semana')
            inicio = datos.get('hora_inicio')
            fin = datos.get('hora_fin')

        if self.instance and barbero.id != self.instance.barbero_id:
            raise ValidationError({'barbero': 'No se puede cambiar el barbero de un horario'})

        if fin <= inicio:
            raise ValidationError({
                "hora_fin": "La hora final debe ser posterior a la inicial"
            })

        horarios = HorarioBarbero.objects.filter(
            barbero = barbero,
            dia_semana = dia,
            hora_inicio__lt = fin,
            hora_fin__gt = inicio
        )

        if self.instance:
            horarios = horarios.exclude(id = self.instance.id)

        if horarios.exists():
            raise ValidationError("El horario se cruza con otro horario del mismo barbero")

        if self.instance:
            restantes = list(HorarioBarbero.objects.filter(barbero=barbero).exclude(
                id=self.instance.id
            ).values('dia_semana', 'hora_inicio', 'hora_fin'))
            restantes.append({'dia_semana': dia, 'hora_inicio': inicio, 'hora_fin': fin})
            validarCoberturaHorarios(barbero, restantes)
        return datos

class BloqueAgendaSerializer(ModelSerializer):
    class Meta:
        model = BloqueAgenda
        fields = '__all__'

    def validate_barbero(self, barbero):
        if not barbero.activo:
            raise ValidationError("El barbero está inactivo")

        return barbero

    def validate(self, datos):
        if self.instance:
            barbero = datos.get('barbero', self.instance.barbero)
            inicio = datos.get('fecha_hora_inicio', self.instance.fecha_hora_inicio)
            fin = datos.get('fecha_hora_fin', self.instance.fecha_hora_fin)
        else:
            barbero = datos.get('barbero')
            inicio = datos.get('fecha_hora_inicio')
            fin = datos.get('fecha_hora_fin')

        if fin <= inicio:
            raise ValidationError({
                "fecha_hora_fin": (
                    "La fecha y hora final debe ser posteriores a la fecha y hora inicial"
                )
            })

        bloqueos = BloqueAgenda.objects.filter(
            barbero = barbero,
            fecha_hora_inicio__lt = fin,
            fecha_hora_fin__gt = inicio
        )

        if self.instance:
            bloqueos = bloqueos.exclude(id = self.instance.id)

        if bloqueos.exists():
            raise ValidationError("El bloqueo se cruza con otro bloqueo del mismo barbero")

        tieneCitas = Cita.objects.filter(
            barbero = barbero,
            estado__in = ['pendiente', 'confirmada', 'pendiente_reprogramacion', 'completada'],
            fecha_hora_inicio__lt = fin,
            fecha_hora_fin__gt = inicio,
        ).exists()

        if tieneCitas:
            raise ValidationError("El bloqueo se cruza con una cita existente")

        return datos

class CitaSerializer(ModelSerializer):
    sede_id = CharField(source='sede.id', read_only=True)
    barbero_id = CharField(source='barbero.id', read_only=True)
    servicio_id = CharField(source='servicio.id', read_only=True)
    sede_nombre = SerializerMethodField()
    barbero_nombre = SerializerMethodField()
    servicio_nombre = SerializerMethodField()

    class Meta:
        model = Cita
        fields = '__all__'
        read_only_fields = (
            'id',
            'codigo_cita',
            'precio',
            'fecha_hora_fin',
            'estado',
            'fecha_hora_registro',
            'fecha_hora_modificacion',
        )
        extra_kwargs = {
            'sede': {'write_only': True},
            'barbero': {'write_only': True},
            'servicio': {'write_only': True},
            'nombre_contacto': {'required': False},
            'email_contacto': {'required': False},
            'telefono_contacto': {'required': False}
        }

    def get_sede_nombre(self, cita):
            return cita.sede.nombre

    def get_barbero_nombre(self, cita):
            return cita.barbero.usuario.nombre

    def get_servicio_nombre(self, cita):
            return cita.servicio.nombre

    def validate_telefono_contacto(self, telefono):
        if len(telefono) != 9 or not all(digito in '0123456789' for digito in telefono):
            raise ValidationError("El teléfono debe contener 9 dígitos")

        return telefono

    def validate(self, datos):
        if self.instance:
            sede = datos.get('sede', self.instance.sede)
            barbero = datos.get('barbero', self.instance.barbero)
            servicio = datos.get('servicio', self.instance.servicio)
            cliente = datos.get('cliente', self.instance.cliente)
            inicio = datos.get('fecha_hora_inicio', self.instance.fecha_hora_inicio)
        else:
            sede = datos.get('sede')
            barbero = datos.get('barbero')
            servicio = datos.get('servicio')
            cliente = datos.get('cliente')
            inicio = datos.get('fecha_hora_inicio')

        if cliente and (not self.instance or 'cliente' in datos):
            usuario = cliente.usuario

            datos['nombre_contacto'] = usuario.nombre
            datos['email_contacto'] = usuario.correo
            datos['telefono_contacto'] = usuario.telefono

        errores = {}

        camposContacto = (
            'nombre_contacto',
            'email_contacto',
            'telefono_contacto'
        )

        for campo in camposContacto:
            if self.instance:
                valor = datos.get(campo, getattr(self.instance, campo))
            else:
                valor = datos.get(campo)

            if not valor or not valor.strip():
                errores[campo] = (
                    "Este dato es obligatorio. Envíalo en el body "
                    "o complétalo en el usuario del cliente"
                )

        if errores:
            raise ValidationError(errores)

        if 'telefono_contacto' in datos:
            self.validate_telefono_contacto(datos['telefono_contacto'])

        if not sede.activo:
            raise ValidationError({
                "sede": "La sede está inactiva"
            })

        if not barbero.activo or not barbero.usuario.is_active:
            raise ValidationError({
                "barbero": "El barbero no pertenece a la sede seleccionada"
            })

        if barbero.sede_id != sede.id:
            raise ValidationError({
                "barbero": "El barbero no pertenece a la sede seleccionada"
            })

        if not servicio.activo:
            raise ValidationError({
                "servicio": "El servicio está inactivo"
            })

        if cliente and not cliente.usuario.is_active:
            raise ValidationError({
                "cliente": "La cuenta del cliente está inactiva"
            })

        servicioSede = ServicioSede.objects.filter(
            sede = sede,
            servicio = servicio,
            disponible = True
        ).first()

        if not servicioSede:
            raise ValidationError({
                "servicio": "El servicio no está disponible en esta sede"
            })

        realizaServicio = BarberoServicio.objects.filter(barbero = barbero,servicio = servicio).exists()

        if not realizaServicio:
            raise ValidationError({
                "barbero": "El barbero no realiza el servicio seleccionado"
            })

        if inicio <= timezone.now():
            raise ValidationError({
                "fecha_hora_inicio": "La cita debe comenzar despues de la hora actual"
            })

        if servicio.duracion <= 0:
            raise ValidationError({
                "servicio": "El Servicio debe tener una duración mayor a cero"
            })

        fin = inicio + timedelta(minutes=servicio.duracion)

        zona = ZoneInfo('America/Lima')
        inicioLocal = timezone.localtime(inicio, zona)
        finLocal = timezone.localtime(fin, zona)

        if inicioLocal.date() != finLocal.date():
            raise ValidationError({
                "fecha_hora_inicio": "La cita debe comenzar y terminar el mismo día"
            })

        tieneHorario = HorarioBarbero.objects.filter(
            barbero = barbero,
            dia_semana = inicioLocal.weekday(),
            hora_inicio__lte = inicioLocal.time(),
            hora_fin__gte = finLocal.time()
        ).exists()

        if not tieneHorario:
            raise ValidationError({
                "fecha_hora_inicio": "La cita debe estar dentro del horario del barbero"
            })

        tieneBloqueo = BloqueAgenda.objects.filter(barbero = barbero, fecha_hora_inicio__lt = fin, fecha_hora_fin__gt = inicio).exists()

        if tieneBloqueo:
            raise ValidationError({
                "fecha_hora_inicio": "El barbero no está disponible en ese período"
            })

        citas = Cita.objects.filter(
            barbero = barbero,
            estado__in = ['pendiente', 'confirmada', 'pendiente_reprogramacion', 'completada'],
            fecha_hora_inicio__lt = fin,
            fecha_hora_fin__gt = inicio,
        )

        if self.instance:
            citas = citas.exclude(id = self.instance.id)

        if citas.exists():
            raise ValidationError({
                "fecha_hora_inicio": "El barbero ya tiene una cita agendada en ese horario"
            })

        datos['fecha_hora_fin'] = fin

        if not self.instance:
            datos['precio'] = servicioSede.precio

        return datos


class HistorialCitaSerializer(ModelSerializer):
    usuario_nombre = SerializerMethodField()

    class Meta:
        model = HistorialCita
        fields = (
            'id',
            'cita',
            'accion',
            'estado_previo',
            'estado_nuevo',
            'inicio_anterior',
            'fin_anterior',
            'inicio_cita',
            'fin_cita',
            'modificado_por',
            'usuario_nombre',
            'tipo_acto',
            'razon',
            'fecha_creacion',
        )
        read_only_fields = fields

    def get_usuario_nombre(self, historial):
        if historial.modificado_por:
            return historial.modificado_por.nombre

        if historial.tipo_acto == 'invitado':
            return 'Invitado'

        return 'Sistema'

class ReprogramarCitaSerializer(Serializer):
    fecha_hora_inicio = DateTimeField()
    razon = CharField(required=False, allow_blank=True, default='')

class CancelarCitaSerializer(Serializer):
    razon = CharField(required=False, allow_blank=True, default='')


class DisponibilidadSerializer(Serializer):
    fecha = DateField()
    sede = PrimaryKeyRelatedField(queryset=Sede.objects.filter(activo=True))
    barbero = PrimaryKeyRelatedField(queryset=Barbero.objects.filter(
        activo=True, usuario__is_active=True, sede__activo=True
    ))
    servicio = PrimaryKeyRelatedField(queryset=Servicio.objects.filter(activo=True))


class CuentaBarberoSerializer(ModelSerializer):
    class Meta:
        model = Usuario
        fields = ('nombre', 'apellido', 'correo', 'telefono', 'sexo', 'password')
        extra_kwargs = {
            'apellido': {'required': False, 'allow_blank': True, 'allow_null': True},
            'password': {'write_only': True, 'min_length': 8},
            'telefono': {'required': True, 'allow_blank': False},
        }

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        if password is not None:
            instance.set_password(password)
            instance.save(update_fields=['password'])
        return instance


class HorarioInicialSerializer(Serializer):
    dia_semana = IntegerField(min_value=0, max_value=6)
    hora_inicio = TimeField()
    hora_fin = TimeField()

    def validate(self, datos):
        if datos['hora_fin'] <= datos['hora_inicio']:
            raise ValidationError({'hora_fin': 'La hora final debe ser posterior a la inicial'})
        return datos


class RegistroBarberoSerializer(ModelSerializer):
    horarios = HorarioInicialSerializer(many=True, required=False, write_only=True)
    cuenta = CuentaBarberoSerializer(required=False, write_only=True)
    servicios = PrimaryKeyRelatedField(
        queryset=Servicio.objects.filter(activo=True),
        many=True,
        required=False,
        write_only=True
    )

    class Meta:
        model = Barbero
        fields = ('id', 'usuario', 'sede', 'activo', 'cuenta', 'servicios', 'horarios')
        extra_kwargs = {'usuario': {'required': False}}

    def validate(self, datos):
        usuario = datos.get('usuario')
        cuenta = datos.get('cuenta')
        if bool(usuario) == bool(cuenta):
            raise ValidationError('Envía un usuario existente o los datos de una cuenta nueva')
        if usuario and not usuario.is_active:
            raise ValidationError({'usuario': 'El usuario debe estar activo'})
        if usuario and Cliente.objects.filter(usuario=usuario).exists():
            raise ValidationError({'usuario': 'El usuario ya tiene un perfil de Cliente'})
        if not datos['sede'].activo:
            raise ValidationError({'sede': 'La sede está inactiva'})
        servicios = datos.get('servicios', [])
        if len(servicios) != len({servicio.id for servicio in servicios}):
            raise ValidationError({'servicios': 'No repitas el mismo servicio'})
        return datos

    def validate_horarios(self, horarios):
        anteriores = {}
        for horario in sorted(horarios, key=lambda item: (item['dia_semana'], item['hora_inicio'])):
            dia = horario['dia_semana']
            if dia in anteriores and horario['hora_inicio'] < anteriores[dia]:
                raise ValidationError('Los turnos del mismo día no pueden superponerse')
            anteriores[dia] = horario['hora_fin']
        return horarios

    def create(self, datos):
        horarios = datos.pop('horarios', [])
        cuenta = datos.pop('cuenta', None)
        servicios = datos.pop('servicios', [])
        if cuenta:
            password = cuenta.pop('password')
            usuario = Usuario(**cuenta)
            usuario.set_password(password)
            usuario.save()
            datos['usuario'] = usuario
        barbero = Barbero.objects.create(**datos)
        for servicio in servicios:
            BarberoServicio.objects.create(barbero=barbero, servicio=servicio)
        for horario in horarios:
            HorarioBarbero.objects.create(barbero=barbero, **horario)
        return barbero


class BarberoAdministracionSerializer(ModelSerializer):
    nombre = CharField(source='usuario.nombre', read_only=True)
    apellido = CharField(source='usuario.apellido', read_only=True, allow_null=True)
    correo = EmailField(source='usuario.correo', read_only=True)
    telefono = CharField(source='usuario.telefono', read_only=True)
    sexo = CharField(source='usuario.sexo', read_only=True)
    servicios = SerializerMethodField()

    class Meta:
        model = Barbero
        fields = ('id', 'usuario', 'sede', 'activo', 'nombre', 'apellido', 'correo', 'telefono', 'sexo', 'servicios')
        read_only_fields = fields

    def get_servicios(self, barbero):
        return [relacion.servicio_id for relacion in barbero.barberoservicio_set.all()]


class EdicionBarberoSerializer(Serializer):
    sede = PrimaryKeyRelatedField(queryset=Sede.objects.all(), required=False)
    activo = BooleanField(required=False)
    servicios = PrimaryKeyRelatedField(queryset=Servicio.objects.all(), many=True, required=False)


class ResponderReprogramacionSerializer(Serializer):
    aceptada = BooleanField()
    razon = CharField(required=False, allow_blank=True, default='')