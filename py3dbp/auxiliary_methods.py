from decimal import Decimal, ROUND_CEILING
from .constants import Axis


def rectIntersect(item1, item2, x, y):
    d1 = item1.getDimension()
    d2 = item2.getDimension()

    cx1 = item1.position[x] + d1[x]/2
    cy1 = item1.position[y] + d1[y]/2
    cx2 = item2.position[x] + d2[x]/2
    cy2 = item2.position[y] + d2[y]/2

    ix = max(cx1, cx2) - min(cx1, cx2)
    iy = max(cy1, cy2) - min(cy1, cy2)

    return ix < (d1[x]+d2[x])/2 and iy < (d1[y]+d2[y])/2


def intersect(item1, item2):
    return (
        rectIntersect(item1, item2, Axis.WIDTH, Axis.HEIGHT) and
        rectIntersect(item1, item2, Axis.HEIGHT, Axis.DEPTH) and
        rectIntersect(item1, item2, Axis.WIDTH, Axis.DEPTH)
    )


def getLimitNumberOfDecimals(number_of_decimals):
    return Decimal('1.{}'.format('0' * number_of_decimals))


def set2Decimal(value, number_of_decimals=0):
    number_of_decimals = getLimitNumberOfDecimals(number_of_decimals)

    return Decimal(value).quantize(number_of_decimals)


def ceil2Decimal(value, number_of_decimals=0):
    ''' round UP to the given decimals (dimensions derived from folds/compression must never shrink) '''
    # round(...,9) removes float noise such as 20.900000000000002
    return Decimal(repr(round(float(value), 9))).quantize(
        getLimitNumberOfDecimals(number_of_decimals), rounding=ROUND_CEILING)


def overlap(a0, a1, b0, b1):
    ''' length of the intersection of [a0,a1) and [b0,b1) '''
    return max(0.0, min(float(a1), float(b1)) - max(float(a0), float(b0)))
