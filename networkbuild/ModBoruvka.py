# -*- coding: utf-8 -*-

__author__ = 'Brandon Ogle'

import numpy as np
import networkx as nx 

from copy import copy
from rtree import Rtree
from scipy.spatial import cKDTree

from networkbuild.utils import UnionFind, PriorityQueue, hav_dist, cartesian_projection, make_bounding_box, line_subgraph_intersection

def sq_dist(a,b):
    """Calculates square distance to reduce performance overhead of square root"""
    return np.sum((a-b)**2)


def FNNd(kdtree, A, b):
    """
    kdtree -> nodes in subnet -> coord of b -> index of a
    returns nearest foreign neighbor a∈A of b
    """
    a = None
    k = k_cache[str(b)] if str(b) in k_cache else 2
    
    while a not in A:
        _, nn = kdtree.query(b, k=k)
        a = nn[-1]
        k += 1
    
    k_cache[str(b)] = k-1
    #return NN a ∈ A of b 
    return a


def modBoruvka(T, subgraphs=None, rtree=None):

    global k_cache
    k_cache = {}

    V = T.nodes(data=False)
    coords = np.row_stack(nx.get_node_attributes(T, 'coords').values())
    projcoords = cartesian_projection(coords)
    
    kdtree = cKDTree(projcoords)

    if subgraphs is None:
        if rtree != None: raise ValueError('RTree passed without UnionFind')
        
        rtree = Rtree()
        # modified to handle queues, children, mv
        subgraphs = UnionFind(T)

    # Tests whether the node is a projection on the existing grid, using its MV
    is_fake = lambda n: subgraphs.mv[n] == np.inf

    #                ∀ v∈V 
    # find the nearest neighbor for all nodes, 
    # initialize a singleton subgraph and populate
    # its a queue with the nn edge where dist is priority
    for v in V:
        vm = FNNd(kdtree, V, projcoords[v]) 
        dm = sq_dist(coords[v], coords[vm])
        
        root = subgraphs[v]
    
        subgraphs.queues[root].push((v,vm), dm)
        
    Et = [] # Initialize MST edges to empty list 
    
    # MST is complete when there are N-1 edges
    while len(Et) < len(V) - 1: #this criteria may need modified 
        # This is an itermediary list of edges that might be added to the MST
        Ep = PriorityQueue()
        #∀ C of T; where C <- connected component
        for C in subgraphs.connected_components():
            
            q_top = subgraphs.queues[C].top()
            try:
                # MV criteria requires pruning of edges, 
                # meaning this priority queue can empty
                (v, vm) = q_top
            except:
                continue
                
            component_set = subgraphs.component_set(v)
            djointVC = list(set(V) - set(component_set))
            
            # vm ∈ C {not a foreign nearest neighbor}
            # go through the queue until a edge is found that connects two subgraphs
            # while in the loop update the items in the queue, 
            # preventing edges between nodes in the same subgraph
            while vm in component_set:
                subgraphs.queues[C].pop()
                um = FNNd(kdtree, djointVC, projcoords[v])
                dm = sq_dist(coords[v], coords[um])
                subgraphs.queues[C].push((v,um), dm)
                (v,vm) = subgraphs.queues[C].top()
            
            # use haversine distance when moving into E', as needed for mv criteria
            dm = hav_dist(coords[v], coords[vm])
            # Append the top priority edge from the subgraph to the intermediary edgelist
            Ep.push((v, vm, dm), dm)
            
        # add all the edges in E' to Et so long as no cycles are created
        state = copy(Et)
        while Ep._queue:
            (um, vm, dm) = Ep.pop()

            # if doesn't create cycle and subgraph has enough MV
            if subgraphs[um] != subgraphs[vm] and (subgraphs.mv[subgraphs[um]] >= dm or is_fake(um)): 
                # test that the connecting subgraph can receive the MV
                if subgraphs.mv[subgraphs[vm]] >= dm or is_fake(vm):
                    # both two way tests passed
                    subgraphs.union(um, vm, dm)
                    
                    # doesn't create cycles from line segment intersection
                    invalid_edge, intersections = line_subgraph_intersection(subgraphs, rtree, coords[um], coords[vm])

                    if not invalid_edge:
                        # valid edges should not intersect any subgraph more than once
                        assert(filter(lambda n: n > 1, intersections.values()) == [])
                        
                        # For all intersected subgraphs update the mv to that created by the edge intersecting them,
                        # TODO: This should be updated in not such a naive method
                        map(lambda (n, _): subgraphs.union(um, n, 0), 
                                filter(lambda (n, i): i == 1 and subgraphs[n] != subgraphs[um], intersections.iteritems()))

                        # index the newly added edge
                        box = make_bounding_box(coords[um], coords[vm])

                        # Object is in form of (u.label, v.label), (u.coord, v.coord)
                        rtree.insert(hash((um, vm)), box, obj=((um, vm), (coords[um], coords[vm])))
                        Et += [(um, vm)]

            else:
                # This edge subgraph will never be able to connect
                # No reason to test this edge further
                try:
                    subgraphs.queues[um].pop()
                except:
                    pass
       
        if Et == state:
            break
    
    T.remove_edges_from(T.edges())
    T.add_edges_from(Et)
    return T
