from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class Paginacion(PageNumberPagination):
    page_size = 5
    page_size_query_param = "cantidad"
    max_page_size = 10
    page_query_param = "pagina"
    invalid_page_message = "Página inválida"

    def get_paginated_response(self, data):
        return Response(data={
            "content": data,
            "paginacion": {
                "total": self.page.paginator.count,
                "pagina_actual": self.page.number,
                "total_paginas": self.page.paginator.num_pages,
                "siguiente": self.get_next_link(),
                "anterior": self.get_previous_link()
            }
        })