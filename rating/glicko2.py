"""Glicko-2, implementado desde el paper de Mark Glickman.

Referencia: "Example of the Glicko-2 system", M. Glickman (2022).
http://www.glicko.net/glicko/glicko2.pdf

Este archivo no sabe nada de F1: recibe jugadores y partidas, y devuelve
ratings actualizados. La lógica de F1 (quién se enfrenta con quién) vive
en build_ranking.py.

Vocabulario:
- rating (r): nivel estimado, en la escala clásica (1500 = promedio).
- rd: desviación del rating, o cuánta incertidumbre tenemos sobre r.
- vol (σ): volatilidad, o qué tan errático es el desempeño del jugador.
Internamente, Glicko-2 trabaja en otra escala (μ, φ); se convierte al
entrar y al salir.
"""

import math
from dataclasses import dataclass

SCALE = 173.7178        # factor de conversión entre la escala clásica y la de Glicko-2
DEFAULT_RATING = 1500.0
DEFAULT_RD = 350.0
DEFAULT_VOL = 0.06
TAU = 0.5               # cuánto puede cambiar la volatilidad entre períodos (paper: 0.3 a 1.2)
EPSILON = 1e-6          # tolerancia del método numérico para la volatilidad


@dataclass
class Player:
    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    vol: float = DEFAULT_VOL

    @property
    def mu(self) -> float:
        return (self.rating - DEFAULT_RATING) / SCALE

    @property
    def phi(self) -> float:
        return self.rd / SCALE

    @property
    def conservative(self) -> float:
        """Rating con margen de seguridad: lo que el piloto vale con ~95% de confianza."""
        return self.rating - 2 * self.rd


@dataclass
class Game:
    opponent: Player   # el rival, con su rating ANTES del período
    score: float       # 1 = ganó, 0 = perdió, 0.5 = empate


def _g(phi: float) -> float:
    """Reduce el peso de un rival cuyo rating es incierto."""
    return 1 / math.sqrt(1 + 3 * phi**2 / math.pi**2)


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    """Probabilidad esperada de ganarle al rival j."""
    return 1 / (1 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _new_volatility(phi: float, vol: float, v: float, delta: float) -> float:
    """Paso 5 del paper: resuelve la nueva volatilidad (algoritmo de Illinois).

    Si el resultado del período fue muy distinto de lo esperado (delta grande
    respecto de v), la volatilidad sube: el jugador es más impredecible de lo
    que creíamos.
    """
    a = math.log(vol**2)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta**2 - phi**2 - v - ex)
        den = 2 * (phi**2 + v + ex) ** 2
        return num / den - (x - a) / TAU**2

    big_a = a
    if delta**2 > phi**2 + v:
        big_b = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        big_b = a - k * TAU

    f_a, f_b = f(big_a), f(big_b)
    while abs(big_b - big_a) > EPSILON:
        big_c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(big_c)
        if f_c * f_b <= 0:
            big_a, f_a = big_b, f_b
        else:
            f_a /= 2
        big_b, f_b = big_c, f_c

    return math.exp(big_a / 2)


def update(player: Player, games: list[Game]) -> Player:
    """Devuelve el nuevo estado del jugador después de un período de rating.

    Un período sin partidas solo aumenta la incertidumbre (rd): el nivel
    estimado no cambia, pero sabemos menos del jugador. Así se modela un hiato.
    """
    mu, phi, vol = player.mu, player.phi, player.vol

    if not games:
        new_phi = math.sqrt(phi**2 + vol**2)
        return Player(player.rating, min(new_phi * SCALE, DEFAULT_RD), vol)

    # Paso 3: varianza estimada (v) a partir de los resultados del período.
    # Paso 4: mejora estimada (delta) respecto de lo esperado.
    v_inv = 0.0
    delta_sum = 0.0
    for game in games:
        g = _g(game.opponent.phi)
        e = _expected(mu, game.opponent.mu, game.opponent.phi)
        v_inv += g**2 * e * (1 - e)
        delta_sum += g * (game.score - e)
    v = 1 / v_inv
    delta = v * delta_sum

    # Pasos 5 a 7: volatilidad, incertidumbre previa al período y actualización final.
    new_vol = _new_volatility(phi, vol, v, delta)
    phi_star = math.sqrt(phi**2 + new_vol**2)
    new_phi = 1 / math.sqrt(1 / phi_star**2 + 1 / v)
    new_mu = mu + new_phi**2 * delta_sum

    return Player(new_mu * SCALE + DEFAULT_RATING, new_phi * SCALE, new_vol)
