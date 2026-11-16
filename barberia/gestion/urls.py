from django.urls import path
from .views import listarBarberos, disponibilidad, BarberoDetalleView
from .views import SedesView, SedeDetalleView, registroUsuario, login, perfilUsuario, registroBarbero, registroCliente, ServiciosView, ServiciosSedeView, ServicioSedeDetalleView, BarberoServiciosView, BarberoServicioDetalleView, HorariosBarberosView, HorarioBarberoDetalleView, BloqueoAgendaView, CitasView, confirmarCita, historialCita, detalleCita, cancelarCita,completarCita,reprogramarCita,BloqueoAgendaDetalleView, responderReprogramacion,marcarNoAsistio

urlpatterns = [
    path('barbero/<uuid:id>', BarberoDetalleView.as_view()),
    path('disponibilidad', disponibilidad),
    path('barberos', listarBarberos),
    path('sedes', SedesView.as_view()),
    path('sede/<uuid:id>', SedeDetalleView.as_view()),
    path('registro', registroUsuario),
    path('login', login),
    path('perfil', perfilUsuario),
    path('registro-barbero', registroBarbero),
    path('registro-cliente', registroCliente),
    path('servicios', ServiciosView.as_view()),
    path('servicios-sedes', ServiciosSedeView.as_view()),
    path('servicio-sede/<uuid:id>', ServicioSedeDetalleView.as_view()),
    path('barberos-servicios', BarberoServiciosView.as_view()),
    path('barbero-servicio/<uuid:id>', BarberoServicioDetalleView.as_view()),
    path('horarios-barberos', HorariosBarberosView.as_view()),
    path('horario-barbero/<uuid:id>', HorarioBarberoDetalleView.as_view()),
    path('bloqueos-agenda', BloqueoAgendaView.as_view()),
    path('citas', CitasView.as_view()),
    path('cita/<uuid:id>/confirmar', confirmarCita),
    path('cita/<uuid:id>/historial', historialCita),
    path('cita/<uuid:id>', detalleCita),
    path('cita/<uuid:id>/cancelar', cancelarCita),
    path('cita/<uuid:id>/completar', completarCita),
    path('cita/<uuid:id>/reprogramar', reprogramarCita),
    path('bloqueo-agenda/<uuid:id>', BloqueoAgendaDetalleView.as_view()),
    path('cita/<uuid:id>/responder-reprogramacion', responderReprogramacion),
    path('cita/<uuid:id>/no-asistio', marcarNoAsistio)
]
