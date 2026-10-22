
def fmt(v, casas=3) -> str:
    """Formata numero para exibicao."""
    if v is None:
        return "-"

    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)

    if not np.isfinite(f):
        return "-"

    return (
        f"{f:,.{casas}f}"
        .replace(",", "@")
        .replace(".", ",")
        .replace("@", ".")
    )
