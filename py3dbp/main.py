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
                 fold_count=0, compress_ratio=1.0, quantity=1, sku=None):
        '''
        WHD    : for stacks (quantity > 1, fold_count > 0 or compress_ratio < 1) it is the size of ONE piece:
                 W = length, H = width, D = thickness. The pieces are stacked along D (laid flat).
        weight : for stacks, the weight of ONE piece.
        fold_count     : how many times the piece may be folded in half (on its length or on its width).
                         Every fold halves W or H and doubles the thickness.
        compress_ratio : 0 < r <= 1. Thickness of a piece inside the stack = thickness * r (1 = incompressible).
        quantity       : number of identical pieces represented by this item.
        '''
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
        self.is_stack = self.quantity > 1 or self.fold_count > 0 or self.compress_ratio < 1
        self.piece_whd = (float(WHD[0]), float(WHD[1]), float(WHD[2]))
        self.unit_weight = float(weight)
        self.fold_state = 0
        if self.is_stack:
            # a stack is always laid flat: thickness stays vertical, only length/width may swap
            self.updown = False
            self.setShape(0, self.quantity)


    def foldStates(self):
        '''
        All shapes of ONE piece, least folded first:
        [(w, h, thickness_in_stack, folds_on_length, folds_on_width), ...]
        '''
        W, H, D = self.piece_whd
        states = []
        for n in range(self.fold_count + 1):
            for a in range(n, -1, -1):
                b = n - a
                states.append((W / 2 ** a, H / 2 ** b, D * 2 ** n * self.compress_ratio, a, b))
        return states


    def setShape(self, fold_state, quantity):
        ''' set width/height/depth/weight of a stack with `quantity` pieces in the given fold state '''
        w, h, t, _, _ = self.foldStates()[fold_state]
        nd = self.number_of_decimals
        self.fold_state = fold_state
        self.quantity = quantity
        self.width = ceil2Decimal(w, nd)
        self.height = ceil2Decimal(h, nd)
        self.depth = ceil2Decimal(t * quantity, nd)
        self.weight = ceil2Decimal(self.unit_weight * quantity, nd)


    def foldDescription(self):
        ''' human readable fold state '''
        _, _, _, a, b = self.foldStates()[self.fold_state]
        parts = []
        if a:
            parts.append('{}x no comprimento'.format(a))
        if b:
            parts.append('{}x na largura'.format(b))
        return 'dobrada ' + ' e '.join(parts) if parts else 'sem dobra'


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

    def __init__(self, partno, WHD, max_weight,corner=0,put_type=1):
        ''' '''
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
        return (
            pivot[0] + dimension[0] <= self.width and
            pivot[1] + dimension[1] <= self.height and
            pivot[2] + dimension[2] <= self.depth
        )


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


    def _putStack(self, item, pivot):
        '''
        Put as many pieces of the stack as fit on this pivot, as a single column.
        Fold states are tried from the least folded to the most folded, so a piece is only
        folded when the unfolded shape does not fit. The caller decreases item.quantity by the
        quantity actually placed (self.items[-1].quantity).
        '''
        z0 = float(pivot[2])
        room_weight = float(self.max_weight) - float(self.getTotalWeight())
        max_by_weight = math.floor(room_weight / item.unit_weight + 1e-9) if item.unit_weight > 0 else item.quantity
        if max_by_weight < 1:
            return False

        for fold_state, (w, h, t, _, _) in enumerate(item.foldStates()):
            for rotation in RotationType.Notupdown:
                piece = copy.copy(item)
                piece.rotation_type = rotation
                piece.position = pivot
                piece.setShape(fold_state, 1)
                if not self._inside(pivot, piece.getDimension()):
                    continue
                k = min(item.quantity, max_by_weight, math.floor((float(self.depth) - z0) / t + 1e-9))
                while k >= 1:
                    piece.setShape(fold_state, k)
                    if not self._inside(pivot, piece.getDimension()):
                        k -= 1
                        continue
                    if self.getTotalWeight() + piece.weight > self.max_weight:
                        k -= 1
                        continue
                    blockers = [o for o in self.items if intersect(o, piece)]
                    if not blockers:
                        break
                    # something above the pivot limits the column height
                    z_block = min(float(o.position[2]) for o in blockers)
                    if z_block <= z0:
                        k = 0
                        break
                    k = min(k - 1, math.floor((z_block - z0) / t + 1e-9))
                if k < 1:
                    continue
                dimension = piece.getDimension()
                if self._settle(piece, pivot, dimension) is None:
                    continue
                self._commit(piece, dimension)
                return True
        return False


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
            # fix height
            y = self.checkHeight([x,x+float(w),y,y+float(h),z,z+float(d)])
            # fix width
            x = self.checkWidth([x,x+float(w),y,y+float(h),z,z+float(d)])
            # fix depth
            z = self.checkDepth([x,x+float(w),y,y+float(h),z,z+float(d)])

        # check stability on item
        # rule :
        # 1. Define a support ratio, if the ratio below the support surface does not exceed this ratio, compare the second rule.
        # 2. If there is no support under any vertices of the bottom of the item, then fit = False.
        if self.check_stable == True :
            # Cal the surface area of the item.
            item_area_lower = float(w) * float(h)
            # Cal the surface area of the underlying support.
            support_area_upper = 0
            for s in self.fit_items:
                # Verify that the lower support surface area is greater than the upper support surface area * support_surface_ratio.
                if z == s[5]  :
                    support_area_upper += overlap(x, x+float(w), s[0], s[1]) * overlap(y, y+float(h), s[2], s[3])

            # If not , get four vertices of the bottom of the item.
            if item_area_lower > 0 and support_area_upper / item_area_lower < self.support_surface_ratio :
                four_vertices = [[x,y],[x+float(w),y],[x,y+float(h)],[x+float(w),y+float(h)]]
                #  If any vertices is not supported, fit = False.
                c = [False,False,False,False]
                for s in self.fit_items:
                    if z == s[5] :
                        for jdx,j in enumerate(four_vertices) :
                            if (s[0] <= j[0] <= s[1]) and (s[2] <= j[1] <= s[3]) :
                                c[jdx] = True
                if False in c :
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
            response = bin.putItem(item, list(START_POSITION))

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

