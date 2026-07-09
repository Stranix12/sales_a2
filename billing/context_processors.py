"""Context processors de billing."""


def cart_badge(request):
    """Expone cart_count (total de unidades en el carrito de sesión) a todos
    los templates, para el badge del sidebar. El carrito solo existe para
    usuarios del portal; para el resto la suma da 0 y el badge no se pinta."""
    cart = request.session.get('cart') or {}
    try:
        count = sum(int(v) for v in cart.values())
    except (TypeError, ValueError):
        count = 0
    return {'cart_count': count}
