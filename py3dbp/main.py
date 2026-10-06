from .constants import RotationType, Axis
from .auxiliary_methods import intersect, set2Decimal, ceil2Decimal, overlap
import numpy as np
import math
import copy
DEFAULT_NUMBER_OF_DECIMALS = 0
START_POSITION = [0, 0, 0]


def _load_matplotlib():
    ''' matplotlib is only needed by Painter: import it lazily so the packing core runs without it '''
    global Rectangle, Circle, plt, art3d
    from matplotlib.patches import Rectangle, Circle
    import matplotlib.pyplot as plt
    import mpl_toolkits.mplot3d.art3d as art3d



class Item:

    def __init__(self, partno,name,typeof, WHD, weight, level, loadbear, updown, color,
                 fold_count=0, compress_ratio=1.0, quantity=1, sku=None, bendable=False, squeeze=1.0):
        '''
        WHD    : for stacks (quantity > 1, fold_count > 0 or compress_ratio < 1) it is the size of ONE piece:
                 W = length, H = width, D = thickness. The pieces are stacked along D (laid flat).
        weight : for stacks, the weight of ONE piece.
        fold_count     : how many times the piece may be folded in half (on its length or on its width).
                         Every fold halves W or H and doubles the thickness.
        compress_ratio : 0 < r <= 1. Thickness of a piece inside the stack = thickness * r (1 = incompressible).
        quantity       : number of identical pieces represented by this item.
        bendable       : the piece may be bent at 90 degrees (L shape, laid flat) to take a corner
                         when the straight shape does not fit.
        squeeze        : 0 < s <= 1. Lateral compression: length and width of a piece may be squeezed
                         to s of their size (e.g. two trousers side by side in a slightly narrower bale).
                         Only used when the piece does not fit at its normal size.
        '''
        if not 0 < squeeze <= 1:
            raise ValueError('squeeze must be in (0, 1]')
        if not 0 < compress_ratio <= 1:
            raise ValueError('compress_ratio must be in (0, 1]')
        if int(fold_count) != fold_count or fold_count < 0:
            raise ValueError('fold_count must be an integer >= 0')
        if int(quantity) != quantity or quantity < 1:
            raise ValueError('quantity must be an integer >= 1')
        self.partno = partno
        self.name = name
        self.typeof = typeof
        self.sku = sku if sku is not None else name
        self.width = WHD[0]
        self.height = WHD[1]
        self.depth = WHD[2]
        self.weight = weight
        # Packing Priority level ,choose 1-3
        self.level = level
        # loadbear
        self.loadbear = loadbear
        # Upside down? True or False
        self.updown = updown if typeof == 'cube' else False
        # Draw item color
        self.color = color
        self.rotation_type = 0
        self.position = list(START_POSITION)
        self.number_of_decimals = DEFAULT_NUMBER_OF_DECIMALS
        # --- folding / compression / quantity ---
        self.fold_count = int(fold_count)
        self.compress_ratio = float(compress_ratio)
        self.quantity = int(quantity)
        self.squeeze = float(squeeze)
        self.is_stack = self.quantity > 1 or self.fold_count > 0 or self.compress_ratio < 1 or self.squeeze < 1
        self.piece_whd = (float(WHD[0]), float(WHD[1]), float(WHD[2]))
        self.unit_weight = float(weight)
        self.fold_state = 0
        self.bendable = bool(bendable)
        # L-shaped stacks are placed as two blocks: bend = 'A' (carries quantity and weight) or
        # 'B' (second arm, quantity 0); layers = pieces drawn in the block
        self.bend = None
        self.layers = None
        if self.is_stack:
            # updown=False: the stack is laid flat (thickness vertical, length/width may swap).
            # updown=True : the pieces may also stand on edge, the stack then grows sideways.
            self.setShape(0, self.quantity)


    def foldStates(self):
        '''
        All shapes of ONE piece, least folded first:
        [(w, h, thickness_in_stack, folds_on_length, folds_on_width), ...]
        With lateral compression (squeeze < 1) every fold state is followed by its squeezed version,
        so a piece is squeezed before being folded and only when the normal size does not fit.
        '''
        cache = self.__dict__.get('_fold_states')
        if cache is not None:
            return cache
        W, H, D = self.piece_whd
        states = []
        squeezed = set()
        for n in range(self.fold_count + 1):
            for a in range(n, -1, -1):
                b = n - a
                states.append((W / 2 ** a, H / 2 ** b, D * 2 ** n * self.compress_ratio, a, b))
                if self.squeeze < 1:
                    squeezed.add(len(states))
                    states.append((W / 2 ** a * self.squeeze, H / 2 ** b * self.squeeze,
                                   D * 2 ** n * self.compress_ratio, a, b))
        self._fold_states = states
        self._squeezed_states = squeezed
        return states


    def isSqueezed(self):
        self.foldStates()
        return self.fold_state in self.__dict__.get('_squeezed_states', ())


    def setShape(self, fold_state, quantity):
        ''' set width/height/depth/weight of a stack with `quantity` pieces in the given fold state '''
        nd = self.number_of_decimals
        # cache shared by the copies of the item (copy.copy keeps the same dict)
        cache = self.__dict__.setdefault('_shape_cache', {})
        key = (fold_state, quantity, nd)
        shape = cache.get(key)
        if shape is None:
            w, h, t, _, _ = self.foldStates()[fold_state]
            shape = cache[key] = (ceil2Decimal(w, nd), ceil2Decimal(h, nd),
                                  ceil2Decimal(t * quantity, nd), ceil2Decimal(self.unit_weight * quantity, nd))
        self.fold_state = fold_state
        self.quantity = quantity
        self.width, self.height, self.depth, self.weight = shape


    def foldDescription(self):
        ''' human readable fold state '''
        _, _, _, a, b = self.foldStates()[self.fold_state]
        parts = []
        if a:
            parts.append('{}x no comprimento'.format(a))
        if b:
            parts.append('{}x na largura'.format(b))
        texto = 'dobrada ' + ' e '.join(parts) if parts else 'sem dobra'
        if self.isSqueezed():
            texto += ', comprimida na lateral'
        return texto


    def formatNumbers(self, number_of_decimals):
        ''' '''
        self.number_of_decimals = number_of_decimals
        if self.is_stack:
            self.setShape(self.fold_state, self.quantity)
            return
        self.width = set2Decimal(self.width, number_of_decimals)
        self.height = set2Decimal(self.height, number_of_decimals)
        self.depth = set2Decimal(self.depth, number_of_decimals)
        self.weight = set2Decimal(self.weight, number_of_decimals)


    def string(self):
        ''' '''
        extra = ' qty(%s) %s' % (self.quantity, self.foldDescription()) if self.is_stack else ''
        return "%s(%sx%sx%s, weight: %s) pos(%s) rt(%s) vol(%s)%s" % (
            self.partno, self.width, self.height, self.depth, self.weight,
            self.position, self.rotation_type, self.getVolume(), extra
        )


    def getVolume(self):
        ''' '''
        return set2Decimal(self.width * self.height * self.depth, self.number_of_decimals)


    def getMaxArea(self):
        ''' '''
        a = sorted([self.width,self.height,self.depth],reverse=True) if self.updown == True else [self.width,self.height,self.depth]

        return set2Decimal(a[0] * a[1] , self.number_of_decimals)


    def getDimension(self):
        ''' rotation type '''
        if self.rotation_type == RotationType.RT_WHD:
            dimension = [self.width, self.height, self.depth]
        elif self.rotation_type == RotationType.RT_HWD:
            dimension = [self.height, self.width, self.depth]
        elif self.rotation_type == RotationType.RT_HDW:
            dimension = [self.height, self.depth, self.width]
        elif self.rotation_type == RotationType.RT_DHW:
            dimension = [self.depth, self.height, self.width]
        elif self.rotation_type == RotationType.RT_DWH:
            dimension = [self.depth, self.width, self.height]
        elif self.rotation_type == RotationType.RT_WDH:
            dimension = [self.width, self.depth, self.height]
        else:
            dimension = []

        return dimension



class Bin:

    def __init__(self, partno, WHD, max_weight,corner=0,put_type=1,shape='box',mask=None,mask_cell=1.0):
        '''
        shape='cylinder': W is the diameter (H must be equal to W), D the height. Items must fit
        inside the circle.
        shape='mask'    : the floor is a grid of square cells of `mask_cell` (cm); `mask[i][j]` says
        whether the cell i (along W) x j (along H) belongs to the container. An item fits when every
        cell under its footprint (even partially covered) belongs to it. Any outline (rounded
        rectangle, outline traced from a photo, ...) becomes a mask.
        Packing strategies can be tuned with:
          stack_rotations : preference order of the rotation types tried for stacks
          fold_first      : try the most folded shape first
        '''
        if shape not in ('box', 'cylinder', 'mask'):
            raise ValueError("shape must be 'box', 'cylinder' or 'mask'")
        self.shape = shape
        self.mask_cell = float(mask_cell)
        self._mask_sat = None
        if shape == 'mask':
            if mask is None:
                raise ValueError("shape='mask' needs a mask")
            m = np.asarray(mask, dtype=bool)
            # summed-area table: number of cells inside any rectangle in O(1)
            self._mask_sat = np.zeros((m.shape[0] + 1, m.shape[1] + 1), dtype=np.int64)
            self._mask_sat[1:, 1:] = m.astype(np.int64).cumsum(0).cumsum(1)
            self.mask = m
        self.stack_rotations = None
        # axes a stack may grow along (0 = W, 1 = H, 2 = D); None = any. E.g. {2}: pieces always laid flat
        self.stack_axes = None
        # try the laterally squeezed shapes before the normal ones
        self.squeeze_first = False
        self.fold_first = False
        self.partno = partno
        self.width = WHD[0]
        self.height = WHD[1]
        self.depth = WHD[2]
        self.max_weight = max_weight
        self.corner = corner
        self.items = []
        self.fit_items = np.array([[0,WHD[0],0,WHD[1],0,0]])
        self.unfitted_items = []
        self.number_of_decimals = DEFAULT_NUMBER_OF_DECIMALS
        self.fix_point = False
        self.check_stable = False
        self.support_surface_ratio = 0
        self.put_type = put_type
        # used to put gravity distribution
        self.gravity = []


    def formatNumbers(self, number_of_decimals):
        ''' '''
        self.width = set2Decimal(self.width, number_of_decimals)
        self.height = set2Decimal(self.height, number_of_decimals)
        self.depth = set2Decimal(self.depth, number_of_decimals)
        self.max_weight = set2Decimal(self.max_weight, number_of_decimals)
        self.number_of_decimals = number_of_decimals


    def string(self):
        ''' '''
        return "%s(%sx%sx%s, max_weight:%s) vol(%s)" % (
            self.partno, self.width, self.height, self.depth, self.max_weight,
            self.getVolume()
        )


    def getVolume(self):
        ''' '''
        return set2Decimal(
            self.width * self.height * self.depth, self.number_of_decimals
        )


    def getTotalWeight(self):
        ''' '''
        total_weight = 0

        for item in self.items:
            total_weight += item.weight

        return set2Decimal(total_weight, self.number_of_decimals)


    def _inside(self, pivot, dimension):
        if not (
            pivot[0] + dimension[0] <= self.width and
            pivot[1] + dimension[1] <= self.height and
            pivot[2] + dimension[2] <= self.depth
        ):
            return False
        if self.shape == 'cylinder':
            # the footprint corners must be inside the circle
            r = float(self.width) / 2
            x0, y0 = float(pivot[0]) - r, float(pivot[1]) - r
            x1, y1 = x0 + float(dimension[0]), y0 + float(dimension[1])
            far_x, far_y = max(abs(x0), abs(x1)), max(abs(y0), abs(y1))
            return far_x * far_x + far_y * far_y <= r * r + 1e-6
        if self.shape == 'mask':
            return self._maskCovers(float(pivot[0]), float(pivot[1]), float(dimension[0]), float(dimension[1]))
        return True


    def _maskCovers(self, x, y, w, h):
        ''' every cell under [x, x+w) x [y, y+h) belongs to the mask '''
        c = self.mask_cell
        nx, ny = self.mask.shape
        i0, j0 = int(math.floor(x / c + 1e-9)), int(math.floor(y / c + 1e-9))
        i1, j1 = int(math.ceil((x + w) / c - 1e-9)), int(math.ceil((y + h) / c - 1e-9))
        if i0 < 0 or j0 < 0 or i1 > nx or j1 > ny:
            return False
        if i1 <= i0 or j1 <= j0:
            return True
        sat = self._mask_sat
        inside = sat[i1, j1] - sat[i0, j1] - sat[i1, j0] + sat[i0, j0]
        return bool(inside == (i1 - i0) * (j1 - j0))


    def seedPivots(self):
        '''
        extra pivots on the floor of a cylinder: the pivots next to the items often fall outside
        the circle, so a grid of points inside it is tried too
        '''
        if self.shape == 'box':
            return []
        if getattr(self, '_seeds', None) is None:
            n = 8
            nd = self.number_of_decimals
            seeds = []
            if self.shape == 'mask':
                # first cell of the mask on each row, plus a coarse grid inside it
                c = self.mask_cell
                nx, ny = self.mask.shape
                pts = set()
                for j in range(ny):
                    cols = np.flatnonzero(self.mask[:, j])
                    if cols.size:
                        pts.add((int(cols[0]), j))
                stride_x, stride_y = max(1, nx // n), max(1, ny // n)
                for i in range(0, nx, stride_x):
                    for j in range(0, ny, stride_y):
                        if self.mask[i, j]:
                            pts.add((i, j))
                for i, j in sorted(pts, key=lambda q: (q[1], q[0])):
                    seeds.append([set2Decimal(i * c, nd), set2Decimal(j * c, nd), set2Decimal(0, nd)])
            else:
                d = float(self.width)
                step = d / n
                for j in range(n):
                    for i in range(n):
                        x, y = i * step, j * step
                        if self._inside([x, y, 0], [step / 4, step / 4, 0]):
                            seeds.append([set2Decimal(x, nd), set2Decimal(y, nd), set2Decimal(0, nd)])
            self._seeds = seeds
        return self._seeds


    def _collides(self, item):
        for current_item_in_bin in self.items:
            if intersect(current_item_in_bin, item):
                return True
        return False


    def putItem(self, item, pivot,axis=None,rotations=None):
        '''
        put item in bin. Tries every allowed rotation (or only `rotations`) and, for stacks, every
        fold state before giving up on this pivot.
        '''
        if item.is_stack:
            return self._putStack(item, pivot)

        valid_item_position = item.position
        rotate = RotationType.ALL if item.updown == True else RotationType.Notupdown
        if rotations is not None:
            rotate = [r for r in rotate if r in rotations]
        for rotation in rotate:
            item.rotation_type = rotation
            dimension = item.getDimension()
            if not self._inside(pivot, dimension):
                continue
            item.position = pivot
            if self._collides(item):
                continue
            # cal total weight (no rotation changes the weight)
            if self.getTotalWeight() + item.weight > self.max_weight:
                item.position = valid_item_position
                return False
            position = self._settle(item, pivot, dimension)
            if position is None:
                continue
            self._commit(item, dimension)
            return True

        item.position = valid_item_position
        return False


    def _stackRotations(self, item):
        ''' rotations a stack may take: free or flat (item.updown), limited by stack_axes '''
        if self.stack_axes is not None:
            return [r for r in RotationType.ALL if self.STACK_AXIS[r] in self.stack_axes]
        return RotationType.ALL if item.updown else RotationType.Notupdown


    # axis along which a stack grows (where its `depth` lands) for each rotation type
    STACK_AXIS = {RotationType.RT_WHD: 2, RotationType.RT_HWD: 2, RotationType.RT_HDW: 1,
                  RotationType.RT_WDH: 1, RotationType.RT_DHW: 0, RotationType.RT_DWH: 0}

    def _putStack(self, item, pivot):
        '''
        Put as many pieces of the stack as fit on this pivot, as a single column (laid flat) or row
        (pieces standing on edge, when item.updown is True).
        Fold states are tried from the least folded to the most folded (or the reverse with
        fold_first), so a piece is only folded when the unfolded shape does not fit. The caller
        decreases item.quantity by the quantity actually placed (self.items[-1].quantity).
        '''
        room_weight = float(self.max_weight) - float(self.getTotalWeight())
        max_by_weight = math.floor(room_weight / item.unit_weight + 1e-9) if item.unit_weight > 0 else item.quantity
        if max_by_weight < 1:
            return False
        bin_dims = [float(self.width), float(self.height), float(self.depth)]
        allowed = self._stackRotations(item)
        order = self.stack_rotations or RotationType.ALL
        rotations = [r for r in order if r in allowed]
        folds = list(enumerate(item.foldStates()))
        if self.fold_first:
            folds.reverse()
        if self.squeeze_first:
            # laterally squeezed shapes first (stable sort keeps the fold order)
            apertadas = item.__dict__.get('_squeezed_states', ())
            folds.sort(key=lambda f: f[0] not in apertadas)

        for fold_state, (w, h, t, _, _) in folds:
            for rotation in rotations:
                axis = self.STACK_AXIS[rotation]
                a0 = float(pivot[axis])
                piece = copy.copy(item)
                piece.rotation_type = rotation
                piece.position = pivot
                piece.setShape(fold_state, 1)
                if not self._inside(pivot, piece.getDimension()):
                    continue
                k = min(item.quantity, max_by_weight, math.floor((bin_dims[axis] - a0) / t + 1e-9))
                while k >= 1:
                    piece.setShape(fold_state, k)
                    if not self._inside(pivot, piece.getDimension()):
                        # the larger the stack, the larger the block: binary search the largest k inside
                        lo, hi = 0, k - 1
                        while lo < hi:
                            mid = (lo + hi + 1) // 2
                            piece.setShape(fold_state, mid)
                            if self._inside(pivot, piece.getDimension()):
                                lo = mid
                            else:
                                hi = mid - 1
                        k = lo
                        continue
                    if self.getTotalWeight() + piece.weight > self.max_weight:
                        k -= 1
                        continue
                    blockers = [o for o in self.items if intersect(o, piece)]
                    if not blockers:
                        break
                    # something ahead of the pivot (on the growth axis) limits the stack
                    a_block = min(float(o.position[axis]) for o in blockers)
                    if a_block <= a0:
                        k = 0
                        break
                    k = min(k - 1, math.floor((a_block - a0) / t + 1e-9))
                if k < 1:
                    continue
                dimension = piece.getDimension()
                if self._settle(piece, pivot, dimension) is None:
                    continue
                self._commit(piece, dimension)
                return True
        return self._putBent(item, pivot, max_by_weight)


    def _putBent(self, item, pivot, max_by_weight):
        '''
        L-shaped stack: the pieces are bent at 90 degrees and laid flat, taking a corner.
        Arm A runs along x (a x width), arm B along y (width x (b - width)); a + b = length + width,
        so the area of the piece is kept. Only tried when no straight shape fits on this pivot.
        The four corner positions of the L inside its a x b bounding box are tried.
        '''
        if not (item.bendable and item.is_stack):
            return False
        if self.stack_axes is not None and 2 not in self.stack_axes:
            return False    # the L is laid flat on the floor: only when stacks may grow upwards
        length, width, _ = item.piece_whd
        t = item.foldStates()[0][2]
        nd = self.number_of_decimals
        px, py, pz = (float(v) for v in pivot)
        room_x, room_y = float(self.width) - px, float(self.height) - py
        k_max = min(item.quantity, max_by_weight, math.floor((float(self.depth) - pz) / t + 1e-9))
        if k_max < 1:
            return False
        total = length + width
        candidatos = []
        for a in (min(room_x, length), total - min(room_y, length), total / 2):
            a = math.floor(a * 10) / 10
            b = total - a
            if a >= width + 1 and b >= width + 1 and a <= room_x + 1e-9 and b <= room_y + 1e-9:
                candidatos.append((a, b))
        for a, b in dict.fromkeys(candidatos):
            for corner in ('BL', 'BR', 'TL', 'TR'):
                ay = 0 if corner in ('BL', 'BR') else b - width
                bx = 0 if corner in ('BL', 'TL') else a - width
                by = width if corner in ('BL', 'BR') else 0
                arms = [('A', px, py + ay, a, width), ('B', px + bx, py + by, width, b - width)]
                k = k_max
                while k >= 1:
                    height = ceil2Decimal(t * k, nd)
                    blocks = []
                    for part, x, y, w, h in arms:
                        blk = copy.copy(item)
                        blk.rotation_type = RotationType.RT_WHD
                        blk.setShape(0, k)
                        blk.width, blk.height, blk.depth = ceil2Decimal(w, nd), ceil2Decimal(h, nd), height
                        blk.position = [set2Decimal(x, nd), set2Decimal(y, nd), set2Decimal(pz, nd)]
                        blk.bend, blk.layers = part, k
                        if part == 'B':
                            blk.quantity = 0
                            blk.weight = set2Decimal(0, nd)
                        blocks.append(blk)
                    if not all(self._inside(blk.position, blk.getDimension()) for blk in blocks):
                        k = 0
                        break
                    if self.getTotalWeight() + blocks[0].weight > self.max_weight:
                        k -= 1
                        continue
                    blockers = [o for blk in blocks for o in self.items if intersect(o, blk)]
                    if not blockers:
                        break
                    z_block = min(float(o.position[2]) for o in blockers)
                    if z_block <= pz + 1e-9:
                        k = 0
                        break
                    k = min(k - 1, math.floor((z_block - pz) / t + 1e-9))
                if k < 1:
                    continue
                if self.fix_point and self.check_stable and not all(
                        self._supported(float(blk.position[0]), float(blk.position[1]), pz,
                                        float(blk.width), float(blk.height)) for blk in blocks):
                    continue
                # arm B first: the caller reads the placed quantity from self.items[-1] (arm A)
                for blk in reversed(blocks):
                    self._commit(blk, blk.getDimension())
                return True
        return False


    def _supported(self, x, y, z, w, h):
        '''
        stability rule:
        1. Define a support ratio, if the ratio below the support surface does not exceed this ratio, compare the second rule.
        2. If there is no support under any vertices of the bottom of the item, then fit = False.
        '''
        # Cal the surface area of the item.
        item_area_lower = w * h
        # Cal the surface area of the underlying support.
        support_area_upper = 0
        for s in self.fit_items:
            # Verify that the lower support surface area is greater than the upper support surface area * support_surface_ratio.
            if abs(z - s[5]) < 1e-6 :
                support_area_upper += overlap(x, x+w, s[0], s[1]) * overlap(y, y+h, s[2], s[3])

        # If not , get four vertices of the bottom of the item.
        if item_area_lower > 0 and support_area_upper / item_area_lower < self.support_surface_ratio :
            four_vertices = [[x,y],[x+w,y],[x,y+h],[x+w,y+h]]
            #  If any vertices is not supported, fit = False.
            c = [False,False,False,False]
            for s in self.fit_items:
                if abs(z - s[5]) < 1e-6 :
                    for jdx,j in enumerate(four_vertices) :
                        if (s[0] <= j[0] <= s[1]) and (s[2] <= j[1] <= s[3]) :
                            c[jdx] = True
            if False in c :
                return False
        return True


    def _settle(self, item, pivot, dimension):
        '''
        fix point float prob + stability rule. Sets item.position and returns it, or returns None
        (position restored to pivot) when the item would be unstable or would collide after being
        pushed by fix point.
        '''
        item.position = pivot
        if self.fix_point != True:
            return pivot

        [w,h,d] = dimension
        [x,y,z] = [float(pivot[0]),float(pivot[1]),float(pivot[2])]

        for _ in range(3):
            if self.shape == 'box':   # pushing towards x=0 / y=0 would leave a circle or mask
                # fix height
                y = self.checkHeight([x,x+float(w),y,y+float(h),z,z+float(d)])
                # fix width
                x = self.checkWidth([x,x+float(w),y,y+float(h),z,z+float(d)])
            # fix depth
            z = self.checkDepth([x,x+float(w),y,y+float(h),z,z+float(d)])

        # check stability on item
        if self.check_stable == True and not self._supported(x, y, z, float(w), float(h)):
            return None

        nd = self.number_of_decimals
        item.position = [set2Decimal(x, nd),set2Decimal(y, nd),set2Decimal(z, nd)]
        # fix point only looks at 1-D gaps, so the pushed position may overlap another item
        if item.position != pivot and self._collides(item):
            item.position = pivot
            return None
        return item.position


    def _commit(self, item, dimension):
        [w,h,d] = dimension
        [x,y,z] = [float(item.position[0]),float(item.position[1]),float(item.position[2])]
        self.fit_items = np.append(self.fit_items,np.array([[x,x+float(w),y,y+float(h),z,z+float(d)]]),axis=0)
        placed = copy.deepcopy(item)
        if not placed.is_stack:
            placed.quantity = 1
        self.items.append(placed)


    # ------------------------------------------------------------------ top compaction
    def _top(self, item):
        return float(item.position[2]) + float(item.getDimension()[2])


    def contentTop(self):
        return max((self._top(i) for i in self.items), default=0.0)


    def contentBounds(self):
        ''' (min_x, min_y, max_x, max_y, max_z) of the content '''
        if not self.items:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        mnx = mny = math.inf
        ex = ey = ez = 0.0
        for i in self.items:
            w, h, d = (float(v) for v in i.getDimension())
            x, y, z = (float(v) for v in i.position)
            mnx, mny = min(mnx, x), min(mny, y)
            ex, ey, ez = max(ex, x + w), max(ey, y + h), max(ez, z + d)
        return mnx, mny, ex, ey, ez


    def contentEnvelope(self):
        '''
        volume of the box around the content: what a flexible container (bale) is charged by.
        In a cylinder the footprint is fixed by the circle, so only the height counts.
        '''
        mnx, mny, ex, ey, ez = self.contentBounds()
        if self.shape in ('cylinder', 'mask'):
            # the outline is fixed by the circle / mask: only the height counts
            return float(self.width) * float(self.height) * ez
        return (ex - mnx) * (ey - mny) * ez


    def _rebuildFitItems(self):
        self.fit_items = np.array([[0,float(self.width),0,float(self.height),0,0]])
        for it in self.items:
            w, h, d = it.getDimension()
            x, y, z = (float(v) for v in it.position)
            self.fit_items = np.append(self.fit_items, np.array([[x,x+float(w),y,y+float(h),z,z+float(d)]]), axis=0)


    def _shapes(self, item):
        ''' every shape the item may take: rotations (and, for stacks, fold states) keeping its quantity '''
        if item.is_stack:
            rotations = self._stackRotations(item)
            for fold_state in range(len(item.foldStates())):
                for rotation in rotations:
                    c = copy.copy(item)
                    c.rotation_type = rotation
                    c.setShape(fold_state, item.quantity)
                    yield c
        else:
            for rotation in (RotationType.ALL if item.updown else RotationType.Notupdown):
                c = copy.copy(item)
                c.rotation_type = rotation
                yield c


    def _pivots(self):
        nd = self.number_of_decimals
        pivots = [[set2Decimal(0, nd)] * 3] + list(self.seedPivots())
        for ib in self.items:
            w, h, d = ib.getDimension()
            x, y, z = ib.position
            pivots += [[x + w, y, z], [x, y + h, z], [x, y, z + d]]
        return pivots


    def _placeLowest(self, item):
        '''
        best fit: put the item where the content envelope grows least, then where its top ends
        lowest (then nearest to the origin)
        '''
        best = None
        mnx, mny, ex, ey, ez = self.contentBounds()
        cyl = self.shape in ('cylinder', 'mask')
        for shape in self._shapes(item):
            dims = shape.getDimension()
            for pivot in self._pivots():
                if not self._inside(pivot, dims):
                    continue
                shape.position = pivot
                if self._collides(shape):
                    continue
                pos = self._settle(shape, pivot, dims)
                if pos is None or not self._inside(pos, dims):
                    continue
                top = float(pos[2]) + float(dims[2])
                x0, y0 = float(pos[0]), float(pos[1])
                env = (1.0 if cyl else (max(ex, x0 + float(dims[0])) - min(mnx, x0))
                       * (max(ey, y0 + float(dims[1])) - min(mny, y0))) * max(ez, top)
                key = (round(env, 3), top, float(pos[2]), float(pos[1]), float(pos[0]))
                if best is None or key < best[0]:
                    best = (key, copy.copy(shape), dims)
        if best is None:
            return False
        self._commit(best[1], best[2])
        return True


    def compactTop(self, max_rounds=6):
        '''
        Shrink the content (useful when the container follows the content, e.g. bales).
        The stacks that define the top are taken out and put back where the content envelope grows
        least, in any allowed shape, whole or split in two. Repeats while the envelope (or, with the
        same envelope, the top) goes down; a round that does not improve is undone.
        '''
        for _ in range(max_rounds):
            if not self.items:
                return
            top = self.contentTop()
            envelope = self.contentEnvelope()
            tops = [i for i in self.items if abs(self._top(i) - top) < 1e-6]
            if any(i.bend for i in tops) or len(tops) == len(self.items) and len(tops) == 1 and not tops[0].is_stack:
                return
            saved_items, saved_fit = self.items, self.fit_items
            rest = [i for i in self.items if all(i is not t for t in tops)]
            best = None
            for split in (False, True):
                self.items = list(rest)
                self._rebuildFitItems()
                ok = True
                for it in sorted(tops, key=lambda i: float(i.getVolume()), reverse=True):
                    parts = [it]
                    if split and it.is_stack and it.quantity >= 2:
                        first = it.quantity - it.quantity // 2
                        parts = []
                        for q in (first, it.quantity - first):
                            c = copy.copy(it)
                            c.setShape(it.fold_state, q)
                            parts.append(c)
                    for part in parts:
                        if not self._placeLowest(part):
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    continue
                score = (round(self.contentEnvelope(), 3), round(self.contentTop(), 6))
                if score < (round(envelope, 3), round(top, 6) - 1e-6) and (best is None or score < best[0]):
                    best = (score, self.items, self.fit_items)
            if best is None:
                self.items, self.fit_items = saved_items, saved_fit
                return
            _, self.items, self.fit_items = best


    def checkDepth(self,unfix_point):
        ''' fix item position z '''
        z_ = [[0,0],[float(self.depth),float(self.depth)]]
        for j in self.fit_items:
            # find intersection on x and y.
            if overlap(j[0], j[1], unfix_point[0], unfix_point[1]) > 0 and overlap(j[2], j[3], unfix_point[2], unfix_point[3]) > 0 :
                z_.append([float(j[4]),float(j[5])])
        top_depth = unfix_point[5] - unfix_point[4]
        # find diff set on z_.
        z_ = sorted(z_, key = lambda z_ : z_[1])
        for j in range(len(z_)-1):
            if z_[j+1][0] -z_[j][1] >= top_depth:
                return z_[j][1]
        return unfix_point[4]


    def checkWidth(self,unfix_point):
        ''' fix item position x '''
        x_ = [[0,0],[float(self.width),float(self.width)]]
        for j in self.fit_items:
            # find intersection on z and y.
            if overlap(j[4], j[5], unfix_point[4], unfix_point[5]) > 0 and overlap(j[2], j[3], unfix_point[2], unfix_point[3]) > 0 :
                x_.append([float(j[0]),float(j[1])])
        top_width = unfix_point[1] - unfix_point[0]
        # find diff set on x_bottom and x_top.
        x_ = sorted(x_,key = lambda x_ : x_[1])
        for j in range(len(x_)-1):
            if x_[j+1][0] -x_[j][1] >= top_width:
                return x_[j][1]
        return unfix_point[0]


    def checkHeight(self,unfix_point):
        '''fix item position y '''
        y_ = [[0,0],[float(self.height),float(self.height)]]
        for j in self.fit_items:
            # find intersection on x and z.
            if overlap(j[0], j[1], unfix_point[0], unfix_point[1]) > 0 and overlap(j[4], j[5], unfix_point[4], unfix_point[5]) > 0 :
                y_.append([float(j[2]),float(j[3])])
        top_height = unfix_point[3] - unfix_point[2]
        # find diff set on y_bottom and y_top.
        y_ = sorted(y_,key = lambda y_ : y_[1])
        for j in range(len(y_)-1):
            if y_[j+1][0] -y_[j][1] >= top_height:
                return y_[j][1]

        return unfix_point[2]


    def addCorner(self):
        '''add container coner '''
        if self.corner != 0 :
            corner = set2Decimal(self.corner)
            corner_list = []
            for i in range(8):
                a = Item(
                    partno='corner{}'.format(i),
                    name='corner',
                    typeof='cube',
                    WHD=(corner,corner,corner),
                    weight=0,
                    level=0,
                    loadbear=0,
                    updown=True,
                    color='#000000')

                corner_list.append(a)
            return corner_list


    def putCorner(self,info,item):
        '''put coner in bin '''
        fit = False
        x = set2Decimal(self.width - self.corner)
        y = set2Decimal(self.height - self.corner)
        z = set2Decimal(self.depth - self.corner)
        pos = [[0,0,0],[0,0,z],[0,y,z],[0,y,0],[x,y,0],[x,0,0],[x,0,z],[x,y,z]]
        item.position = pos[info]
        self.items.append(item)

        corner = [float(item.position[0]),float(item.position[0])+float(self.corner),float(item.position[1]),float(item.position[1])+float(self.corner),float(item.position[2]),float(item.position[2])+float(self.corner)]

        self.fit_items = np.append(self.fit_items,np.array([corner]),axis=0)
        return


    def clearBin(self):
        ''' clear item which in bin '''
        self.items = []
        self.fit_items = np.array([[0,self.width,0,self.height,0,0]])
        return


class Packer:

    def __init__(self):
        ''' '''
        self.bins = []
        self.items = []
        self.unfit_items = []
        self.total_items = 0
        self.binding = []
        # self.apex = []


    def addBin(self, bin):
        ''' '''
        return self.bins.append(bin)


    def addItem(self, item):
        ''' '''
        self.total_items = len(self.items) + 1

        return self.items.append(item)


    def pack2Bin(self, bin, item,fix_point,check_stable,support_surface_ratio):
        ''' pack item to bin. Returns True when (part of) the item was placed. '''
        fitted = False
        bin.fix_point = fix_point
        bin.check_stable = check_stable
        bin.support_surface_ratio = support_surface_ratio

        # first put item on (0,0,0) , if corner exist ,first add corner in box.
        if bin.corner != 0 and not bin.items:
            corner_lst = bin.addCorner()
            for i in range(len(corner_lst)) :
                bin.putCorner(i,corner_lst[i])

        elif not bin.items:
            response = False
            for pivot in [list(START_POSITION)] + bin.seedPivots():
                response = bin.putItem(item, pivot)
                if response:
                    break

            if not response:
                bin.unfitted_items.append(item)
            return response

        # rigid items: try the preferred rotation on every pivot before turning the item,
        # so an item is only rotated when it does not fit anywhere as it is
        if item.is_stack:
            rotation_rounds = [None]
        else:
            rotation_rounds = [[r] for r in (RotationType.ALL if item.updown == True else RotationType.Notupdown)]
        for rotations in rotation_rounds:
            for axis in range(0, 3):
                items_in_bin = bin.items
                for ib in items_in_bin:
                    pivot = [0, 0, 0]
                    w, h, d = ib.getDimension()
                    if axis == Axis.WIDTH:
                        pivot = [ib.position[0] + w,ib.position[1],ib.position[2]]
                    elif axis == Axis.HEIGHT:
                        pivot = [ib.position[0],ib.position[1] + h,ib.position[2]]
                    elif axis == Axis.DEPTH:
                        pivot = [ib.position[0],ib.position[1],ib.position[2] + d]

                    if bin.putItem(item, pivot, axis, rotations):
                        fitted = True
                        break
                if fitted:
                    break
            if not fitted:
                for pivot in bin.seedPivots():
                    if bin.putItem(item, pivot, None, rotations):
                        fitted = True
                        break
            if fitted:
                break
        if not fitted:
            bin.unfitted_items.append(item)
        return fitted


    def packItem(self, bin, item, fix_point, check_stable, support_surface_ratio):
        '''
        Pack one item. Stacks are split into columns until they are fully placed or nothing
        else fits; item.quantity ends with the number of pieces still unpacked.
        '''
        while item.quantity > 0:
            if not self.pack2Bin(bin, item, fix_point, check_stable, support_surface_ratio):
                return
            item.quantity -= bin.items[-1].quantity
            if item.is_stack and item.quantity > 0:
                item.position = list(START_POSITION)
                item.rotation_type = 0
                item.setShape(0, item.quantity)


    def sortBinding(self,bin):
        ''' sorted by binding '''
        b,front,back = [],[],[]
        for i in range(len(self.binding)):
            b.append([])
            for item in self.items:
                if item.name in self.binding[i]:
                    b[i].append(item)
                elif item.name not in self.binding:
                    if len(b[0]) == 0 and item not in front:
                        front.append(item)
                    elif item not in back and item not in front:
                        back.append(item)

        min_c = min([len(i) for i in b])

        sort_bind =[]
        for i in range(min_c):
            for j in range(len(b)):
                sort_bind.append(b[j][i])

        for i in b:
            for j in i:
                if j not in sort_bind:
                    self.unfit_items.append(j)

        self.items = front + sort_bind + back
        return


    def putOrder(self):
        '''Arrange the order of items '''
        r = []
        for i in self.bins:
            # open top container
            if i.put_type == 2:
                i.items.sort(key=lambda item: item.position[0], reverse=False)
                i.items.sort(key=lambda item: item.position[1], reverse=False)
                i.items.sort(key=lambda item: item.position[2], reverse=False)
            # general container
            elif i.put_type == 1:
                i.items.sort(key=lambda item: item.position[1], reverse=False)
                i.items.sort(key=lambda item: item.position[2], reverse=False)
                i.items.sort(key=lambda item: item.position[0], reverse=False)
            else :
                pass
        return


    def gravityCenter(self,bin):
        '''
        Deviation Of Cargo gravity distribution: % of the weight on each quarter of the floor
        [front-left, front-right, back-left, back-right]. The weight of an item is split by the
        area of its footprint that lies on each quarter.
        '''
        W = float(bin.width)
        H = float(bin.height)
        quarters = [(0, W/2, 0, H/2), (W/2, W, 0, H/2), (0, W/2, H/2, H), (W/2, W, H/2, H)]
        r = [0.0, 0.0, 0.0, 0.0]

        for i in bin.items:
            w, h, _ = [float(v) for v in i.getDimension()]
            x0, y0 = float(i.position[0]), float(i.position[1])
            area = w * h
            if area <= 0:
                continue
            for j, (qx0, qx1, qy0, qy1) in enumerate(quarters):
                r[j] += overlap(x0, x0 + w, qx0, qx1) * overlap(y0, y0 + h, qy0, qy1) / area * float(i.weight)

        total = sum(r)
        if total == 0:
            return [0, 0, 0, 0]
        return [round(v / total * 100, 2) for v in r]


    def pack(self, bigger_first=False,distribute_items=True,fix_point=True,check_stable=True,support_surface_ratio=0.75,binding=None,number_of_decimals=DEFAULT_NUMBER_OF_DECIMALS):
        '''pack master func '''
        binding = list(binding) if binding else []
        # set decimals
        for bin in self.bins:
            bin.formatNumbers(number_of_decimals)

        for item in self.items:
            item.formatNumbers(number_of_decimals)
        # add binding attribute
        self.binding = binding
        # Bin : sorted by volumn
        self.bins.sort(key=lambda bin: bin.getVolume(), reverse=bigger_first)
        # Item : sorted by volumn -> sorted by loadbear -> sorted by level -> binding
        self.items.sort(key=lambda item: item.getVolume(), reverse=bigger_first)
        # self.items.sort(key=lambda item: item.getMaxArea(), reverse=bigger_first)
        self.items.sort(key=lambda item: item.loadbear, reverse=True)
        self.items.sort(key=lambda item: item.level, reverse=False)
        # sorted by binding
        if binding != []:
            self.sortBinding(bin)

        for idx,bin in enumerate(self.bins):
            # distribute_items=False: every bin gets all the items, so work on a copy
            items = self.items if distribute_items else copy.deepcopy(self.items)
            # pack item to bin
            for item in (copy.deepcopy(items) if binding != [] else items):
                self.packItem(bin, item, fix_point, check_stable, support_surface_ratio)

            if binding != []:
                # resorted
                items.sort(key=lambda item: item.getVolume(), reverse=bigger_first)
                items.sort(key=lambda item: item.loadbear, reverse=True)
                items.sort(key=lambda item: item.level, reverse=False)
                # clear bin
                bin.items = []
                bin.unfitted_items = self.unfit_items
                bin.fit_items = np.array([[0,bin.width,0,bin.height,0,0]])
                # repacking
                for item in items:
                    self.packItem(bin, item,fix_point,check_stable,support_surface_ratio)

            # Deviation Of Cargo Gravity Center
            self.bins[idx].gravity = self.gravityCenter(bin)

            if distribute_items :
                # items are tracked by object (not by partno, which may repeat)
                self.items = [item for item in self.items if item.quantity > 0]

        # put order of items
        self.putOrder()

        if self.items != []:
            self.unfit_items = copy.deepcopy(self.items)
            self.items = []



class Painter:

    def __init__(self,bins):
        ''' '''
        _load_matplotlib()
        self.items = bins.items
        self.width = bins.width
        self.height = bins.height
        self.depth = bins.depth


    def _plotCube(self, ax, x, y, z, dx, dy, dz, color='red',mode=2,linewidth=1,text="",fontsize=15,alpha=0.5):
        """ Auxiliary function to plot a cube. code taken somewhere from the web.  """
        xx = [x, x, x+dx, x+dx, x]
        yy = [y, y+dy, y+dy, y, y]
        
        kwargs = {'alpha': 1, 'color': color,'linewidth':linewidth }
        if mode == 1 :
            ax.plot3D(xx, yy, [z]*5, **kwargs)
            ax.plot3D(xx, yy, [z+dz]*5, **kwargs)
            ax.plot3D([x, x], [y, y], [z, z+dz], **kwargs)
            ax.plot3D([x, x], [y+dy, y+dy], [z, z+dz], **kwargs)
            ax.plot3D([x+dx, x+dx], [y+dy, y+dy], [z, z+dz], **kwargs)
            ax.plot3D([x+dx, x+dx], [y, y], [z, z+dz], **kwargs)
        else :
            p = Rectangle((x,y),dx,dy,fc=color,ec='black',alpha = alpha)
            p2 = Rectangle((x,y),dx,dy,fc=color,ec='black',alpha = alpha)
            p3 = Rectangle((y,z),dy,dz,fc=color,ec='black',alpha = alpha)
            p4 = Rectangle((y,z),dy,dz,fc=color,ec='black',alpha = alpha)
            p5 = Rectangle((x,z),dx,dz,fc=color,ec='black',alpha = alpha)
            p6 = Rectangle((x,z),dx,dz,fc=color,ec='black',alpha = alpha)
            ax.add_patch(p)
            ax.add_patch(p2)
            ax.add_patch(p3)
            ax.add_patch(p4)
            ax.add_patch(p5)
            ax.add_patch(p6)
            
            if text != "":
                ax.text( (x+ dx/2), (y+ dy/2), (z+ dz/2), str(text),color='black', fontsize=fontsize, ha='center', va='center')

            art3d.pathpatch_2d_to_3d(p, z=z, zdir="z")
            art3d.pathpatch_2d_to_3d(p2, z=z+dz, zdir="z")
            art3d.pathpatch_2d_to_3d(p3, z=x, zdir="x")
            art3d.pathpatch_2d_to_3d(p4, z=x + dx, zdir="x")
            art3d.pathpatch_2d_to_3d(p5, z=y, zdir="y")
            art3d.pathpatch_2d_to_3d(p6, z=y + dy, zdir="y")


    def _plotCylinder(self, ax, x, y, z, dx, dy, dz, color='red',mode=2,text="",fontsize=10,alpha=0.2):
        """ Auxiliary function to plot a Cylinder  """
        # plot the two circles above and below the cylinder
        p = Circle((x+dx/2,y+dy/2),radius=dx/2,color=color,alpha=0.5)
        p2 = Circle((x+dx/2,y+dy/2),radius=dx/2,color=color,alpha=0.5)
        ax.add_patch(p)
        ax.add_patch(p2)
        art3d.pathpatch_2d_to_3d(p, z=z, zdir="z")
        art3d.pathpatch_2d_to_3d(p2, z=z+dz, zdir="z")
        # plot a circle in the middle of the cylinder
        center_z = np.linspace(0, dz, 10)
        theta = np.linspace(0, 2*np.pi, 10)
        theta_grid, z_grid=np.meshgrid(theta, center_z)
        x_grid = dx / 2 * np.cos(theta_grid) + x + dx / 2
        y_grid = dy / 2 * np.sin(theta_grid) + y + dy / 2
        z_grid = z_grid + z
        ax.plot_surface(x_grid, y_grid, z_grid,shade=False,fc=color,alpha=alpha,color=color)
        if text != "" :
            ax.text( (x+ dx/2), (y+ dy/2), (z+ dz/2), str(text),color='black', fontsize=fontsize, ha='center', va='center')

    def plotBoxAndItems(self,title="",alpha=0.2,write_num=False,fontsize=10):
        """ side effective. Plot the Bin and the items it contains. """
        fig = plt.figure()
        axGlob = plt.axes(projection='3d')
        
        # plot bin 
        self._plotCube(axGlob,0, 0, 0, float(self.width), float(self.height), float(self.depth),color='black',mode=1,linewidth=2,text="")

        counter = 0
        # fit rotation type
        for item in self.items:
            rt = item.rotation_type  
            x,y,z = item.position
            [w,h,d] = item.getDimension()
            color = item.color
            text= item.partno if write_num else ""

            if item.typeof == 'cube':
                 # plot item of cube
                self._plotCube(axGlob, float(x), float(y), float(z), float(w),float(h),float(d),color=color,mode=2,text=text,fontsize=fontsize,alpha=alpha)
            elif item.typeof == 'cylinder':
                # plot item of cylinder
                self._plotCylinder(axGlob, float(x), float(y), float(z), float(w),float(h),float(d),color=color,mode=2,text=text,fontsize=fontsize,alpha=alpha)
            
            counter = counter + 1  

        
        plt.title(title)
        self.setAxesEqual(axGlob)
        return plt


    def setAxesEqual(self,ax):
        '''Make axes of 3D plot have equal scale so that spheres appear as spheres,
        cubes as cubes, etc..  This is one possible solution to Matplotlib's
        ax.set_aspect('equal') and ax.axis('equal') not working for 3D.

        Input
        ax: a matplotlib axis, e.g., as output from plt.gca().'''
        x_limits = ax.get_xlim3d()
        y_limits = ax.get_ylim3d()
        z_limits = ax.get_zlim3d()

        x_range = abs(x_limits[1] - x_limits[0])
        x_middle = np.mean(x_limits)
        y_range = abs(y_limits[1] - y_limits[0])
        y_middle = np.mean(y_limits)
        z_range = abs(z_limits[1] - z_limits[0])
        z_middle = np.mean(z_limits)

        # The plot bounding box is a sphere in the sense of the infinity
        # norm, hence I call half the max range the plot radius.
        plot_radius = 0.5 * max([x_range, y_range, z_range])

        ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
        ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
        ax.set_zlim3d([z_middle - plot_radius, z_middle + plot_radius])

