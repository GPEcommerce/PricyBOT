class LoginRequiredException(Exception):
    """Exceção customizada para indicar que o login é necessário."""
    pass

class EmailVerificationRequiredException(Exception):
    """Exceção para indicar que a verificação por e-mail é necessária."""
    pass