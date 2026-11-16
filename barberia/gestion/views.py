from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny
from .models import Sede, Usuario, Barbero, Cliente, Servicio, ServicioSede, BarberoServicio, HorarioBarbero, BloqueAgenda, Cita, generar_codigo_cita, HistorialCita
from .serializers import SedeSerializer, UsuarioSerializer, LoginSerializer, BarberoSerializer, ClienteSerializer, ServicioSerializer, ServicioSedeSerializer, BarberoServicioSerializer, HorarioBarberoSerializer, BloqueAgendaSerializer, CitaSerializer, HistorialCitaSerializer, ReprogramarCitaSerializer, CancelarCitaSerializer
from rest_framework_simplejwt.tokens import AccessToken
from .pagination import Paginacion
from django.db import connection, reset_queries, transaction, IntegrityError
from django.utils import timezone
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .serializers import DisponibilidadSerializer, RegistroBarberoSerializer, SedeAdministracionSerializer, CuentaBarberoSerializer, BarberoAdministracionSerializer, EdicionBarberoSerializer, validarCoberturaHorarios, ResponderReprogramacionSerializer
# from uuid import uuid4

def rolUsuario(usuario):
    if not usuario.is_authenticated:
        return 'invitado'
    if usuario.is_staff:
        return 'administrador'
    if hasattr(usuario, 'barbero'):
        return 'barbero'
    return 'cliente'


def citasDelUsuario(usuario):
    citas = Cita.objects.all()
    if usuario.is_staff:
        return citas
    if hasattr(usuario, 'barbero'):
        if not usuario.barbero.activo:
            return citas.none()
        return citas.filter(barbero=usuario.barbero)
    return citas.filter(cliente__usuario=usuario)


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
def listarBarberos(request: Request):
    barberos = Barbero.objects.filter(
        activo=True,
        usuario__is_active=True,
        sede__activo=True
    ).select_related('usuario').order_by('usuario__nombre', 'id')

    if request.user.is_staff and request.query_params.get('incluir_inactivos') == 'true':
        barberos = Barbero.objects.select_related('usuario').prefetch_related(
            'barberoservicio_set'
        ).order_by('usuario__nombre', 'id')
        return Response(data={"content": BarberoAdministracionSerializer(instance=barberos, many=True).data})

    return Response(data={
        "content": [
            {
                "id": barbero.id,
                "sede": barbero.sede_id,
                "nombre": barbero.usuario.nombre,
            }
            for barbero in barberos
        ]
    })

class SedesView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get(self, request: Request):
        sedes = Sede.objects.filter(activo=True).order_by('nombre', 'id')
        serializador = SedeSerializer
        if request.user.is_staff and request.query_params.get('incluir_inactivas') == 'true':
            sedes = Sede.objects.order_by('nombre', 'id')
            serializador = SedeAdministracionSerializer
        sedeSerializada = serializador(instance=sedes, many=True)

        return Response(data={
            "content": sedeSerializada.data
        })

    def post(self, request: Request):
        serializador = SedeSerializer(data = request.data)

        if serializador.is_valid():
            serializador.save()

            return Response(data={
                "message": "Sede creada exitosamente",
                "content": serializador.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(data={
                "message": "Error al crear la sede",
                "content": serializador.errors
            }, status=status.HTTP_400_BAD_REQUEST)


class SedeDetalleView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]

    def get(self, request: Request, id):
        sedes = Sede.objects.all()
        if not request.user.is_staff:
            sedes = sedes.filter(activo=True)
        sede = sedes.filter(id=id).first()
        if not sede:
            return Response(data={
                "message": "La sede no existe o no está activa"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = SedeAdministracionSerializer if request.user.is_staff else SedeSerializer
        return Response(data={"content": serializador(instance=sede).data})

    def put(self, request: Request, id):
        return self.actualizar(request, id, parcial=False)

    def patch(self, request: Request, id):
        return self.actualizar(request, id, parcial=True)

    def actualizar(self, request: Request, id, parcial):
        with transaction.atomic():
            sede = Sede.objects.select_for_update().filter(id=id).first()
            if not sede:
                return Response(data={
                    "message": "La sede no existe"
                }, status=status.HTTP_404_NOT_FOUND)
            serializador = SedeAdministracionSerializer(
                instance=sede, data=request.data, partial=parcial
            )
            if not serializador.is_valid():
                return Response(data={
                    "message": "Error al actualizar la sede",
                    "content": serializador.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            serializador.save()
            return Response(data={
                "message": "Sede actualizada correctamente",
                "content": serializador.data
            })

    def delete(self, request: Request, id):
        with transaction.atomic():
            sede = Sede.objects.select_for_update().filter(id=id, activo=True).first()
            if not sede:
                return Response(data={
                    "message": "La sede no existe o está inactiva"
                }, status=status.HTTP_404_NOT_FOUND)
            sede.activo = False
            sede.save(update_fields=['activo'])
            return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(http_method_names=['POST'])
def registroUsuario(request: Request):
    serializador = UsuarioSerializer(data = request.data)

    if serializador.is_valid():
        nombre = serializador.validated_data.get('nombre')
        correo = serializador.validated_data.get('correo')
        password = serializador.validated_data.get('password')
        sexo = serializador.validated_data.get('sexo')
        telefono = serializador.validated_data.get('telefono')

        usuario = Usuario(nombre = nombre, correo = correo, sexo = sexo, telefono = telefono)

        usuario.set_password(password)
        usuario.save()

        return Response(data={
            "message": "Usuario registrado exitosamente"
        }, status=status.HTTP_201_CREATED)
    else:
        return Response(data={
            "message": "Error al crear el usuario",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(http_method_names=['POST'])
def login(request: Request):
    serializador = LoginSerializer(data = request.data)

    if serializador.is_valid():
        correo = serializador.validated_data.get('correo')
        password = serializador.validated_data.get('password')
        usuario = Usuario.objects.filter(correo = correo).first()

        if not usuario:
            return Response(data={
                "message": "El usuario no existe",
                "content": {"correo": ["No encontramos una cuenta con este correo"]}
            }, status=status.HTTP_400_BAD_REQUEST)

        if not usuario.is_active:
            return Response(data={
                "message": "La cuenta está inactiva"
            }, status=status.HTTP_403_FORBIDDEN)

        password = usuario.check_password(password)

        if password:
            token = AccessToken.for_user(usuario)
            return Response(data={
                "token": str(token)
            })
        else:
            return Response(data={
                "message": "Credenciales inválidas",
                "content": {"password": ["La contraseña no es correcta"]}
            }, status=status.HTTP_403_FORBIDDEN)
    else:
        return Response(data={
            "message": "Error al iniciar sesión",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(http_method_names=['GET'])
@permission_classes([IsAuthenticated])
def perfilUsuario(request: Request):
    usuario = request.user
    serializador = UsuarioSerializer(instance = usuario)
    return Response(data={
        "content": serializador.data,
        "rol": rolUsuario(usuario),
        "cliente_id": getattr(getattr(usuario, 'cliente', None), 'id', None),
        "barbero_id": getattr(getattr(usuario, 'barbero', None), 'id', None),
    })

@api_view(http_method_names=['POST'])
@permission_classes([IsAdminUser])
def registroBarbero(request: Request):
    serializador = RegistroBarberoSerializer(data=request.data)
    if not serializador.is_valid():
        return Response(data={
            "message": "Error al registrar el barbero",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            barbero = serializador.save()
    except IntegrityError:
        return Response(data={
            "message": "No se pudo guardar. Verifica que el correo o el usuario no estén registrados"
        }, status=status.HTTP_400_BAD_REQUEST)

    return Response(data={
        "message": "Barbero registrado con su sede y servicios",
        "content": BarberoSerializer(instance=barbero).data
    }, status=status.HTTP_201_CREATED)


@api_view(http_method_names=['POST'])
@permission_classes([IsAuthenticated])
def registroCliente(request: Request):
    usuarioExiste = Usuario.objects.filter(id = request.user.id).first()
    if not usuarioExiste:
        return Response(data={
            "message": "El usuario no existe"
        }, status=status.HTTP_404_NOT_FOUND)

    barberoUsuario = Barbero.objects.filter(usuario = usuarioExiste.id).first()

    if barberoUsuario:
        return Response(data={
            "message": "El usuario ya es un Barbero"
        }, status=status.HTTP_400_BAD_REQUEST)
    request.data['usuario'] = usuarioExiste.id
    serializador = ClienteSerializer( data = request.data)
    if serializador.is_valid():
        serializador.save()

        return Response(data={
            "message": "Cliente creado exitosamente",
            "content": serializador.data
        }, status=status.HTTP_201_CREATED)
    else:
        return Response(data={
            "message": "Error al crear el registro",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
class ServiciosView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]

        return super().get_permissions()

    def get(self, request: Request):
        reset_queries()

        nombre = request.query_params.get('nombre', '').strip()
        servicios = Servicio.objects.filter(activo=True).order_by('nombre', 'id')

        paginador = Paginacion()

        if nombre:
            servicios = servicios.filter(nombre__icontains = nombre)

        resultado = paginador.paginate_queryset(servicios, request, view=self)
        serializador = ServicioSerializer(instance = resultado, many=True)

        respuesta = paginador.get_paginated_response(serializador.data)

        return respuesta

    def post(self, request: Request):
        serializador = ServicioSerializer(data = request.data)

        if serializador.is_valid():
            serializador.save()

            return Response(data={
                "message": "Se creó el servicio correctamente",
                "content": serializador.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(data={
                "message": "Error al crear el servicio",
                "content": serializador.errors
            }, status=status.HTTP_400_BAD_REQUEST)


class ServiciosSedeView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]

        return super().get_permissions()

    def get(self, request: Request):
        serviciosSede = ServicioSede.objects.order_by('id')
        serializador = ServicioSedeSerializer(instance = serviciosSede, many = True)

        return Response(data={
            "content": serializador.data
        }, status=status.HTTP_200_OK)

    def post(self, request: Request):
        serializador = ServicioSedeSerializer(data = request.data)

        if serializador.is_valid():
            serializador.save()

            return Response(data={
                "message": "Servicio agregado a la sede correctamente",
                "content": serializador.data
            }, status=status.HTTP_201_CREATED)

        return Response(data={
            "message": "Error al agregar el servicio a la sede",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ServicioSedeDetalleView(APIView):
    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsAdminUser()]

        return super().get_permissions()

    def get(self, request: Request, id):
        servicioSede = ServicioSede.objects.filter(id = id).first()

        if not servicioSede:
            return Response(data={
                "message": "No hay registro de esta asociación Servicio Sede"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = ServicioSedeSerializer(instance = servicioSede)

        return Response(data={
            "content": serializador.data
        })

    def put(self, request: Request, id):
        return self.update(request, id, parcial=False)

    def patch(self, request: Request, id):
        return self.update(request, id, parcial=True)

    def update(self, request: Request, id, parcial):
        servicioSede = ServicioSede.objects.filter(id = id).first()

        if not servicioSede:
            return Response(data={
                "message": "No hay registro de esta asociación Servicio Sede"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = ServicioSedeSerializer(
            instance = servicioSede,
            data = request.data,
            partial = parcial
        )

        if serializador.is_valid():
            serializador.save()

            return Response(data={
                "message": "Servicio de la sede actualizado correctamente",
                "content": serializador.data
            })

        return Response(data={
            "message": "Error al actualizar el servicio de la sede",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request: Request, id):
        servicioSede = ServicioSede.objects.filter(id = id).first()

        if not servicioSede:
            return Response(data={
                "message": "No hay registro de esta asociación Servicio Sede"
            }, status=status.HTTP_404_NOT_FOUND)

        servicioSede.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class BarberoServiciosView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]

        return super().get_permissions()

    def get(self, request: Request):
        barberosServicios = BarberoServicio.objects.order_by('id')

        serializador = BarberoServicioSerializer(instance = barberosServicios, many=True)

        return Response(data={
            "content": serializador.data
        })

    def post(self, request: Request):
        serializador = BarberoServicioSerializer(data = request.data)

        if serializador.is_valid():
            serializador.save()

            return Response(data={
                "message": "Servicio asignado al barbero correctamente",
                "content": serializador.data
            }, status=status.HTTP_201_CREATED)

        return Response(data={
            "message": "Error al asignar el servicio al barbero",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class BarberoServicioDetalleView(APIView):
    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsAdminUser()]
        
        return super().get_permissions()

    def get(self, request: Request, id):
        barberoServicio = BarberoServicio.objects.filter(id = id).first()

        if not barberoServicio:
            return Response(data={
                "message": "La asociación entre el barbero y el servicio no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = BarberoServicioSerializer(instance = barberoServicio)

        return Response(data={
            "content": serializador.data
        })

    def put(self, request: Request, id):
        return self.update(request, id, parcial=False)

    def patch(self, request: Request, id):
            return self.update(request, id, parcial=True)

    def update(self, request: Request, id, parcial):
        barberoServicio = BarberoServicio.objects.filter(id = id).first()

        if not barberoServicio:
            return Response(data={
                "message": "La asociación entre el barbero y el servicio no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = BarberoServicioSerializer(
            instance = barberoServicio,
            data = request.data,
            partial = parcial
        )

        if serializador.is_valid():
            serializador.save()

            return Response(data={
                "message": "Servicio del barbero actualizado correctamente",
                "content": serializador.data
            })

        return Response(data={
            "message": "Error al actualizar el servicio del barbero",
            "content": serializador.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request: Request, id):
        barberoServicio = BarberoServicio.objects.filter(id = id).first()

        if not barberoServicio:
            return Response(data={
                "message": "La asociación entre el barbero y el servicio no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        barberoServicio.delete()

        return Response(None, status=status.HTTP_204_NO_CONTENT)


class HorariosBarberosView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        
        return super().get_permissions()

    def get(self, request: Request):
        horarios = HorarioBarbero.objects.order_by(
            'barbero_id', 'dia_semana', 'hora_inicio'
        )

        serializador = HorarioBarberoSerializer(instance = horarios, many=True)

        return Response(data={
            "content": serializador.data
        })

    def post(self, request: Request):
        entrada = HorarioBarberoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        with transaction.atomic():
            Barbero.objects.select_for_update().get(id=entrada.validated_data['barbero'].id)
            serializador = HorarioBarberoSerializer(data=request.data)
            serializador.is_valid(raise_exception=True)
            serializador.save()
            return Response(data={
                "message": "Horario registrado correctamente", "content": serializador.data
            }, status=status.HTTP_201_CREATED)

class HorarioBarberoDetalleView(APIView):
    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsAdminUser()]
        
        return super().get_permissions()

    def get(self, request: Request, id):
        horario = HorarioBarbero.objects.filter(id = id).first()

        if not horario:
            return Response(data={
                "message": "El horario no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = HorarioBarberoSerializer(instance = horario)

        return Response(data={
            "content": serializador.data
        })

    def put(self, request: Request, id):
        return self.update(request, id, parcial = False)

    def patch(self, request: Request, id):
        return self.update(request, id, parcial=True)

    def update(self, request: Request, id, parcial):
        with transaction.atomic():
            horario = HorarioBarbero.objects.filter(id=id).first()
            if not horario:
                return Response(data={"message": "El horario no existe"}, status=status.HTTP_404_NOT_FOUND)
            Barbero.objects.select_for_update().get(id=horario.barbero_id)
            horario = HorarioBarbero.objects.select_for_update().filter(id=id).first()
            if not horario:
                return Response(data={"message": "El horario no existe"}, status=status.HTTP_404_NOT_FOUND)
            serializador = HorarioBarberoSerializer(instance=horario, data=request.data, partial=parcial)
            serializador.is_valid(raise_exception=True)
            serializador.save()
            return Response(data={"message": "Horario actualizado correctamente", "content": serializador.data})

    def delete(self, request: Request, id):
        with transaction.atomic():
            horario = HorarioBarbero.objects.filter(id=id).first()
            if not horario:
                return Response(data={"message": "El horario no existe"}, status=status.HTTP_404_NOT_FOUND)
            Barbero.objects.select_for_update().get(id=horario.barbero_id)
            horario = HorarioBarbero.objects.select_for_update().filter(id=id).first()
            if not horario:
                return Response(data={"message": "El horario no existe"}, status=status.HTTP_404_NOT_FOUND)
            restantes = list(HorarioBarbero.objects.filter(barbero_id=horario.barbero_id).exclude(
                id=horario.id
            ).values('dia_semana', 'hora_inicio', 'hora_fin'))
            validarCoberturaHorarios(horario.barbero, restantes)
            horario.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


class BloqueoAgendaView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]

        return [IsAuthenticated()]

    def get(self, request: Request):
        bloqueos = BloqueAgenda.objects.order_by('fecha_hora_inicio')
        if not request.user.is_staff:
            bloqueos = bloqueos.filter(barbero__usuario=request.user, barbero__activo=True)

        serializador = BloqueAgendaSerializer(instance = bloqueos, many = True)

        return Response(data={
            "content": serializador.data
        })

    def post(self, request: Request):
        serializador = BloqueAgendaSerializer(data = request.data)

        if not serializador.is_valid():
            return Response(data={
                "message": "Error al registrar el bloqueo",
                "content": serializador.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            Barbero.objects.select_for_update().get(id=serializador.validated_data['barbero'].id)

            serializador = BloqueAgendaSerializer(data = request.data)

            if not serializador.is_valid():
                return Response(data={
                    "message": "Error al registrar el bloqueo",
                    "content": serializador.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            serializador.save()

            return Response(data={
                "message": "Bloqueo registrado correctamente",
                "content": serializador.data
            }, status=status.HTTP_201_CREATED)


class BloqueoAgendaDetalleView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request: Request, id):
        bloqueo = BloqueAgenda.objects.filter(id = id).first()

        if not bloqueo:
            return Response(data={
                "message": "El bloqueo no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        serializador = BloqueAgendaSerializer(instance = bloqueo)

        return Response(data={
            "content": serializador.data
        })

    def put(self, request: Request, id):
        return self.update(request, id, parcial=False)

    def patch(self, request: Request, id):
        return self.update(request, id, parcial=True)

    def update(self, request: Request, id, parcial):
        with transaction.atomic():
            bloqueo = BloqueAgenda.objects.filter(id=id).first()

            if not bloqueo:
                return Response(data={
                    "message": "El bloqueo no existe"
                }, status=status.HTTP_404_NOT_FOUND)

            Barbero.objects.select_for_update().get(id=bloqueo.barbero_id)

            bloqueo = BloqueAgenda.objects.select_for_update().filter(id=id).first()

            if not bloqueo:
                return Response(data={
                    "message": "El bloqueo no existe"
                }, status=status.HTTP_404_NOT_FOUND)

            serializador = BloqueAgendaSerializer(instance = bloqueo, data= request.data, partial = parcial)

            if not serializador.is_valid():
                return Response(data={
                    "message": "Error al actualizar el bloqueo",
                    "content": serializador.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            barbero = serializador.validated_data.get('barbero', bloqueo.barbero)

            if barbero.id != bloqueo.barbero_id:
                return Response(data={
                    "message": "No se puede cambiar el barbero de un bloqueo"
                }, status=status.HTTP_400_BAD_REQUEST)

            serializador.save()

            return Response(data={
                "message": "bloqueo actualizado correctamente",
                "content": serializador.data
            })

    def delete(self, request: Request, id):
        with transaction.atomic():
            bloqueo = BloqueAgenda.objects.filter(id = id).first()

            if not bloqueo:
                return Response(data={
                    "message": "El bloqueo no existe"
                }, status=status.HTTP_404_NOT_FOUND)

            Barbero.objects.select_for_update().get(id=bloqueo.barbero_id)

            bloqueo = BloqueAgenda.objects.select_for_update().filter(id = id).first()

            if not bloqueo:
                return Response(data={
                    "message": "El bloqueo no existe"
                }, status=status.HTTP_404_NOT_FOUND)

            bloqueo.delete()

            return Response(status=status.HTTP_204_NO_CONTENT)


class CitasView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get(self, request: Request):
        citas = citasDelUsuario(request.user).select_related('sede', 'barbero__usuario', 'servicio').order_by('fecha_hora_inicio', 'id')

        paginador = Paginacion()
        resultado = paginador.paginate_queryset(citas, request, view=self)
        serializador = CitaSerializer(instance = resultado, many = True)
        respuesta = paginador.get_paginated_response(serializador.data)

        return respuesta

    def post(self, request: Request):
        if rolUsuario(request.user) == 'barbero':
            return Response(data={
                "message": "Las reservas se registran desde una cuenta de cliente o administrador"
            }, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            datos = request.data.copy()
            if not request.user.is_authenticated:
                datos.pop('cliente', None)
            elif not request.user.is_staff:
                cliente, creado = Cliente.objects.get_or_create(usuario=request.user)
                datos['cliente'] = str(cliente.id)
                datos['nombre_contacto'] = request.user.nombre
                datos['email_contacto'] = request.user.correo
                datos['telefono_contacto'] = request.user.telefono
            serializador = CitaSerializer(data=datos)

            if not serializador.is_valid():
                return Response(data={
                    "message": "Error al registrar la cita",
                    "content": serializador.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            barbero = Barbero.objects.select_for_update().get(id = serializador.validated_data['barbero'].id)

            # Volvemos a validar después de bloquear al barberi
            serializador = CitaSerializer(data=datos)

            if not serializador.is_valid():
                return Response(data={
                    "message": "Error al registrar la cita",
                    "content": serializador.errors
                },status=status.HTTP_400_BAD_REQUEST)

            for _ in range(5):
                codigo = generar_codigo_cita()

                try:
                    with transaction.atomic():
                        cita = serializador.save(
                            barbero=barbero,
                            codigo_cita=codigo
                        )

                except IntegrityError:
                    if Cita.objects.filter(codigo_cita=codigo).exists():
                        continue

                    raise

                HistorialCita.objects.create(
                    cita=cita,
                    accion='creacion',
                    estado_previo=None,
                    estado_nuevo=cita.estado,
                    inicio_anterior=None,
                    fin_anterior=None,
                    inicio_cita=cita.fecha_hora_inicio,
                    fin_cita=cita.fecha_hora_fin,
                    modificado_por=request.user if request.user.is_authenticated else None,
                    tipo_acto=rolUsuario(request.user),
                    razon='Registro de la cita'
                )

                return Response(data={
                    "message": "Cita registrada correctamente",
                    "content": serializador.data
                }, status=status.HTTP_201_CREATED)

            return Response(data={
                "message": "No se pudo generar el codigo de reserba. Intenta registrar la cita nuevamente"
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(http_method_names=['PATCH'])
@permission_classes([IsAdminUser])
def confirmarCita(request: Request, id):
    with transaction.atomic():
        cita = Cita.objects.select_for_update().filter(id=id).first()

        if not cita:
            return Response(data={
                "message": "La cita no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        if cita.estado != 'pendiente':
            return Response(data={
                "message": "Solo se pueden confirmar citas pendientes"
            }, status=status.HTTP_400_BAD_REQUEST)

        if cita.fecha_hora_inicio <= timezone.now():
            return Response(data={
                "message": "La cita ya comenzó o su fecha ya pasó"
            }, status=status.HTTP_400_BAD_REQUEST)

        estadoPrevio = cita.estado

        cita.estado = 'confirmada'
        cita.save(update_fields=[
            'estado',
            'fecha_hora_modificacion'
        ])

        HistorialCita.objects.create(
            cita=cita,
            accion='confirmacion',
            estado_previo=estadoPrevio,
            estado_nuevo=cita.estado,
            inicio_anterior=cita.fecha_hora_inicio,
            fin_anterior=cita.fecha_hora_fin,
            inicio_cita=cita.fecha_hora_inicio,
            fin_cita=cita.fecha_hora_fin,
            modificado_por=request.user,
            tipo_acto='administrador',
            razon='Confirmación de la cita'
        )

        serializador = CitaSerializer(instance=cita)

        return Response(data={
            "message": "Cita confirmada correctamente",
            "content": serializador.data
        })


def registrarHistorialCita(
        cita,
        usuario,
        accion,
        estadoPrevio,
        inicioAnterior,
        finAnterior,
        razon
):
    HistorialCita.objects.create(
        cita = cita,
        accion = accion,
        estado_previo = estadoPrevio,
        estado_nuevo = cita.estado,
        inicio_anterior = inicioAnterior,
        fin_anterior = finAnterior,
        inicio_cita = cita.fecha_hora_inicio,
        fin_cita = cita.fecha_hora_fin,
        modificado_por = usuario,
        tipo_acto = rolUsuario(usuario),
        razon = razon
    )

@api_view(http_method_names=['GET'])
@permission_classes([IsAuthenticated])
def detalleCita(request: Request, id):
    cita = citasDelUsuario(request.user).select_related('sede', 'barbero__usuario', 'servicio').filter(id = id).first()

    if not cita:
        return Response(data={
            "message": "La cita no existe"
        }, status=status.HTTP_404_NOT_FOUND)

    serializador = CitaSerializer(instance = cita)

    return Response(data={
        "content": serializador.data
    })

@api_view(http_method_names=['PATCH'])
@permission_classes([IsAuthenticated])
def cancelarCita(request: Request, id):
    if rolUsuario(request.user) == 'barbero':
        return Response(data={
            "message": "Esta acción corresponde al cliente o administrador"
        }, status=status.HTTP_403_FORBIDDEN)

    entrada = CancelarCitaSerializer(data = request.data)
    entrada.is_valid(raise_exception=True) # DRF devuelve 400 automáticamente si los datos ingresados son inválidos

    with transaction.atomic():
        cita = citasDelUsuario(request.user).select_for_update().filter(id = id).first()

        if not cita:
            return Response(data={
                "message": "La cita no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        if cita.estado not in ('pendiente', 'confirmada', 'pendiente_reprogramacion'):
            return Response(data={
                "message": "El estado de la cita no permite cancelarla"
            },status=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_staff and cita.fecha_hora_inicio <= timezone.now():
            return Response(data={
                "message": "Solo puedes cancelar citas que aún no comienzan"
            }, status=status.HTTP_400_BAD_REQUEST)

        estadoPrevio = cita.estado

        cita.estado = 'cancelada'
        cita.save(update_fields=['estado', 'fecha_hora_modificacion'])

        registrarHistorialCita(
            cita = cita,
            usuario= request.user,
            accion='cancelacion',
            estadoPrevio=estadoPrevio,
            inicioAnterior=cita.fecha_hora_inicio,
            finAnterior=cita.fecha_hora_fin,
            razon=entrada.validated_data['razon']
        )

        serializador = CitaSerializer(instance = cita)

        return Response(data={
            "message": "Cita cancelada correctamente",
            "content": serializador.data
        })


@api_view(http_method_names=['PATCH'])
@permission_classes([IsAdminUser])
def completarCita(request: Request, id):
    with transaction.atomic():
        cita = Cita.objects.select_for_update().filter(id = id).first()

        if not cita:
            return Response(data={
                "message": "La cita no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        if cita.estado != 'confirmada':
            return Response(data={
                "message": "Solo se pueden completar citas confirmadas"
            }, status=status.HTTP_400_BAD_REQUEST)

        if cita.fecha_hora_fin > timezone.now():
            return Response(data={
                "message": "La cita todavia no ha terminado"
            }, status=status.HTTP_400_BAD_REQUEST)

        estadoPrevio = cita.estado

        cita.estado = 'completada'
        cita.save(update_fields=['estado', 'fecha_hora_modificacion'])

        registrarHistorialCita(
            cita = cita,
            usuario=request.user,
            accion='completada',
            estadoPrevio=estadoPrevio,
            inicioAnterior=cita.fecha_hora_inicio,
            finAnterior=cita.fecha_hora_fin,
            razon='Atención completada'
        )

        serializador = CitaSerializer(instance = cita)

        return Response(data={
            "message": "Cita completada satisfactoriamente",
            "content": serializador.data
        })


@api_view(http_method_names=['PATCH'])
@permission_classes([IsAuthenticated])
def reprogramarCita(request: Request, id):
    if rolUsuario(request.user) == 'barbero':
        return Response(data={
            "message": "Esta acción corresponde al cliente o administrador"
        }, status=status.HTTP_403_FORBIDDEN)

    entrada = ReprogramarCitaSerializer(data = request.data)
    entrada.is_valid(raise_exception=True)

    with transaction.atomic():
        cita = citasDelUsuario(request.user).select_for_update().filter(id = id).first()

        if not cita:
            return Response(data={
                "message": "La cita no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        if cita.estado not in ('pendiente', 'confirmada', 'pendiente_reprogramacion'):
            return Response(data={
                "message": "El estado de esta cita no permite reprogramarla"
            }, status=status.HTTP_400_BAD_REQUEST)

        if cita.fecha_hora_inicio <= timezone.now():
            return Response(data={
                "message": "Solo se pueden reprogramar citas que aún no comienzan"
            }, status=status.HTTP_400_BAD_REQUEST)

        Barbero.objects.select_for_update().get(id = cita.barbero.id)

        nuevoInicio = entrada.validated_data['fecha_hora_inicio']

        if nuevoInicio == cita.fecha_hora_inicio:
            return Response(data={
                "message": "Debes seleccionar una fecha u hora diferente"
            }, status=status.HTTP_400_BAD_REQUEST)

        estadoPrevio = cita.estado
        inicioAnterior = cita.fecha_hora_inicio
        finAnterior = cita.fecha_hora_fin

        serializador = CitaSerializer(instance = cita, data={'fecha_hora_inicio': nuevoInicio}, partial=True)

        if not serializador.is_valid():
            return Response(data={
                "message": "Error al reprogramar la cita",
                "content": serializador.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        if request.user.is_staff:
            nuevoEstado = 'pendiente_reprogramacion'
        else:
            nuevoEstado = 'pendiente'

        cita = serializador.save(estado=nuevoEstado)

        registrarHistorialCita(
            cita = cita,
            usuario=request.user,
            accion='reprogramacion',
            estadoPrevio=estadoPrevio,
            inicioAnterior=inicioAnterior,
            finAnterior=finAnterior,
            razon=entrada.validated_data['razon']
        )

        return Response(data={
            "message": "Cita reprogramada correctamente",
            "content": serializador.data
        })


@api_view(http_method_names=['GET'])
@permission_classes([IsAuthenticated])
def historialCita(request: Request, id):
    cita = citasDelUsuario(request.user).filter(id = id).first()

    if not cita:
        return Response(data={
            "message": "La cita no existe"
        }, status=status.HTTP_404_NOT_FOUND)

    historial = HistorialCita.objects.filter(cita = cita).select_related('modificado_por').order_by('fecha_creacion', "id")

    serializador = HistorialCitaSerializer(instance = historial, many = True)

    return Response(data={
        "content": serializador.data
    })


@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
def disponibilidad(request: Request):
    entrada = DisponibilidadSerializer(data=request.query_params)
    entrada.is_valid(raise_exception=True)
    datos = entrada.validated_data
    barbero = datos['barbero']
    servicio = datos['servicio']
    sede = datos['sede']
    fecha = datos['fecha']

    disponible = ServicioSede.objects.filter(
        sede=sede, servicio=servicio, disponible=True
    ).exists()
    realizaServicio = BarberoServicio.objects.filter(
        barbero=barbero, servicio=servicio
    ).exists()
    if barbero.sede_id != sede.id or not disponible or not realizaServicio:
        return Response(data={"content": []})

    zona = ZoneInfo('America/Lima')
    principio = datetime.combine(fecha, datetime.min.time(), tzinfo=zona)
    final = principio + timedelta(days=1)
    citas = list(Cita.objects.filter(
        barbero=barbero,
        fecha_hora_inicio__lt=final,
        fecha_hora_fin__gt=principio
    ).filter(estado__in=['pendiente', 'confirmada','pendiente_reprogramacion','completada']).values_list('fecha_hora_inicio', 'fecha_hora_fin'))
    bloqueos = list(BloqueAgenda.objects.filter(
        barbero=barbero,
        fecha_hora_inicio__lt=final,
        fecha_hora_fin__gt=principio
    ).values_list('fecha_hora_inicio', 'fecha_hora_fin'))
    horarios = HorarioBarbero.objects.filter(
        barbero=barbero, dia_semana=fecha.weekday()
    ).order_by('hora_inicio')
    horas = {}
    ahora = timezone.now()
    if servicio.duracion <= 0:
        return Response(data={"content": []})

    for horario in horarios:
        inicio = datetime.combine(fecha, horario.hora_inicio, tzinfo=zona)
        limite = datetime.combine(fecha, horario.hora_fin, tzinfo=zona)
        duracion = timedelta(minutes=servicio.duracion)
        while inicio + duracion <= limite:
            fin = inicio + duracion
            ocupado = any(anterior < fin and posterior > inicio for anterior, posterior in citas + bloqueos)
            hora = inicio.strftime('%H:%M')
            horas[hora] = {"hora": hora, "disponible": inicio > ahora and not ocupado}
            inicio += timedelta(minutes=30)

    return Response(data={"content": [horas[hora] for hora in sorted(horas)]})


class BarberoDetalleView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request: Request, id):
        barbero = Barbero.objects.select_related('usuario').prefetch_related(
            'barberoservicio_set'
        ).filter(id=id).first()
        if not barbero:
            return Response(data={"message": "El barbero no existe"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data={"content": BarberoAdministracionSerializer(instance=barbero).data})

    def patch(self, request: Request, id):
        try:
            with transaction.atomic():
                barbero = Barbero.objects.select_for_update().filter(id=id).first()
                if not barbero:
                    return Response(data={"message": "El barbero no existe"}, status=status.HTTP_404_NOT_FOUND)
                usuario = Usuario.objects.select_for_update().get(id=barbero.usuario_id)
                datos = EdicionBarberoSerializer(data=request.data)
                datos.is_valid(raise_exception=True)
                cuenta = CuentaBarberoSerializer(
                    instance=usuario, data=request.data.get('cuenta', {}), partial=True
                )
                cuenta.is_valid(raise_exception=True)
                sede = datos.validated_data.get('sede', barbero.sede)
                servicios = datos.validated_data.get('servicios')
                futuras = Cita.objects.filter(
                    barbero=barbero, estado__in=['pendiente', 'confirmada', 'pendiente_reprogramacion'],
                    fecha_hora_fin__gt=timezone.now()
                )
                if sede.id != barbero.sede_id:
                    if not sede.activo:
                        return Response(data={"message": "La nueva sede está inactiva"}, status=status.HTTP_400_BAD_REQUEST)
                    if futuras.exists():
                        return Response(data={"message": "Reasigna o cancela las citas pendientes antes de cambiar la sede del barbero"}, status=status.HTTP_400_BAD_REQUEST)
                if servicios is not None:
                    ids = {servicio.id for servicio in servicios}
                    if len(ids) != len(servicios):
                        return Response(data={"message": "No repitas servicios"}, status=status.HTTP_400_BAD_REQUEST)
                    actuales = set(BarberoServicio.objects.filter(barbero=barbero).values_list('servicio_id', flat=True))
                    if any(not servicio.activo and servicio.id not in actuales for servicio in servicios):
                        return Response(data={"message": "No puedes asignar un servicio inactivo"}, status=status.HTTP_400_BAD_REQUEST)
                    if futuras.exclude(servicio_id__in=ids).exists():
                        return Response(data={"message": "Hay citas pendientes para los servicios que intentas quitar"}, status=status.HTTP_400_BAD_REQUEST)
                cuenta.save()
                barbero.sede = sede
                barbero.activo = datos.validated_data.get('activo', barbero.activo)
                barbero.save(update_fields=['sede', 'activo'])
                if servicios is not None:
                    BarberoServicio.objects.filter(barbero=barbero).exclude(servicio_id__in=ids).delete()
                    for servicio in servicios:
                        BarberoServicio.objects.get_or_create(barbero=barbero, servicio=servicio)
                return Response(data={
                    "message": "Barbero actualizado correctamente",
                    "content": BarberoAdministracionSerializer(instance=barbero).data
                })
        except IntegrityError:
            return Response(data={"message": "No se pudo guardar. Revisa si el correo ya está registrado"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request: Request, id):
        with transaction.atomic():
            barbero = Barbero.objects.select_for_update().filter(id=id, activo=True).first()
            if not barbero:
                return Response(data={"message": "El barbero no existe o está inactivo"}, status=status.HTTP_404_NOT_FOUND)
            barbero.activo = False
            barbero.save(update_fields=['activo'])
            return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(http_method_names=['PATCH'])
@permission_classes([IsAuthenticated])
def responderReprogramacion(request: Request, id):
    if rolUsuario(request.user) == 'barbero':
        return Response(data={
            "message": "Esta acción corresponde al cliente o administrador"
        }, status=status.HTTP_403_FORBIDDEN)

    entrada = ResponderReprogramacionSerializer(data = request.data)
    entrada.is_valid(raise_exception=True)

    razon = entrada.validated_data['razon'].strip()

    if request.user.is_staff and not razon:
        return Response(data={
            "message": "Indica cómo se obtuvo la respuesta del cliente",
            "content": {
                "razon": ["Registra la respuesta comunicada por el cliente"]
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        cita = citasDelUsuario(request.user).select_for_update().filter(id = id).first()

        if not cita:
            return Response(data={
                "message": "La cita no existe"
            },status=status.HTTP_404_NOT_FOUND)

        if cita.estado != 'pendiente_reprogramacion':
            return Response(data={
                "message": "La cita no tiene una reprogramación por responder"
            }, status=status.HTTP_400_BAD_REQUEST)

        aceptada = entrada.validated_data['aceptada']

        if aceptada and cita.fecha_hora_inicio <= timezone.now():
            return Response(data={
                "message": "El horario propuesto ya pasó. Debe proponerse otro"
            }, status=status.HTTP_400_BAD_REQUEST)

        estadoPrevio = cita.estado
        cita.estado = 'confirmada' if aceptada else 'cancelada'

        cita.save(update_fields=['estado', 'fecha_hora_modificacion'])

        registrarHistorialCita(
            cita = cita,
            usuario=request.user,
            accion=('reprogramacion_aceptada' if aceptada else 'reprogramacion_rechazada'),
            estadoPrevio=estadoPrevio,
            inicioAnterior=cita.fecha_hora_inicio,
            finAnterior=cita.fecha_hora_fin,
            razon=razon
        )

        serializador = CitaSerializer(instance=cita)

        return Response(data={
            "message": "Respuesta registrada correctamente",
            "content": serializador.data
        })


@api_view(http_method_names=['PATCH'])
@permission_classes([IsAdminUser])
def marcarNoAsistio(request: Request, id):
    entrada = CancelarCitaSerializer(data = request.data)
    entrada.is_valid(raise_exception=True)

    with transaction.atomic():
        cita = Cita.objects.select_for_update().filter(id=id).first()

        if not cita:
            return Response(data={
                "message": "La cita no existe"
            }, status=status.HTTP_404_NOT_FOUND)

        if cita.estado != 'confirmada':
            return Response(data={
                "message": "Solo se puede registrar ausencia en citas confirmadas"
            }, status=status.HTTP_400_BAD_REQUEST)

        if cita.fecha_hora_fin > timezone.now():
            return Response(data={
                "message": "Espera a que termine el horario reservado"
            }, status=status.HTTP_400_BAD_REQUEST)

        estadoPrevio = cita.estado
        cita.estado = 'no_asistio'

        cita.save(update_fields=['estado', 'fecha_hora_modificacion'])

        registrarHistorialCita(
            cita=cita,
            usuario=request.user,
            accion='no_asistio',
            estadoPrevio=estadoPrevio,
            inicioAnterior=cita.fecha_hora_inicio,
            finAnterior=cita.fecha_hora_fin,
            razon=entrada.validated_data['razon']
        )

        serializador = CitaSerializer(instance = cita)

        return Response(data={
            "message": "Ausencia registrada correctamente",
            "content": serializador.data
        })
