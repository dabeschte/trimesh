try:
    from . import generic as g
except BaseException:
    import generic as g

from trimesh.scene.transforms import EnforcedForest


def random_chr():
    return chr(ord('a') + int(round(g.np.random.random() * 25)))


class SceneTests(g.unittest.TestCase):

    def test_scene(self):
        for mesh in g.get_mesh('cycloidal.ply',
                               'sphere.ply'):
            if mesh.units is None:
                mesh.units = 'in'

            scene_split = g.trimesh.scene.split_scene(mesh)
            scene_split.convert_units('in')
            scene_base = g.trimesh.Scene(mesh)

            # save MD5 of scene before concat
            pre = [scene_split.md5(), scene_base.md5()]
            # make sure MD5's give the same result twice
            assert scene_split.md5() == pre[0]
            assert scene_base.md5() == pre[1]

            assert isinstance(scene_base.crc(), int)

            # try out scene appending
            concat = scene_split + scene_base

            # make sure concat didn't mess with original scenes
            assert scene_split.md5() == pre[0]
            assert scene_base.md5() == pre[1]

            # make sure concatenate appended things, stuff
            assert len(concat.geometry) == (len(scene_split.geometry) +
                                            len(scene_base.geometry))

            for s in [scene_split, scene_base]:
                pre = s.md5()
                assert len(s.geometry) > 0
                assert s.is_valid

                flattened = s.graph.to_flattened()
                g.json.dumps(flattened)
                edgelist = s.graph.to_edgelist()
                g.json.dumps(edgelist)

                assert s.bounds.shape == (2, 3)
                assert s.centroid.shape == (3,)
                assert s.extents.shape == (3,)
                assert isinstance(s.scale, float)
                assert g.trimesh.util.is_shape(s.triangles, (-1, 3, 3))
                assert len(s.triangles) == len(s.triangles_node)

                assert s.md5() == pre
                assert s.md5() is not None

                # should be some duplicate nodes
                assert len(s.duplicate_nodes) > 0

                # should be a single scene camera
                assert isinstance(s.camera, g.trimesh.scene.cameras.Camera)
                # should be autogenerated lights
                assert len(s.lights) > 0
                # all lights should be lights
                assert all(isinstance(L, g.trimesh.scene.lighting.Light)
                           for L in s.lights)
                # all lights should be added to scene graph
                assert all(L.name in s.graph for L in s.lights)

                # should have put a transform in scene graph
                assert s.camera.name in s.graph

                r = s.dump()

                gltf = s.export(file_type='gltf')
                assert isinstance(gltf, dict)
                assert len(gltf) > 0
                assert len(gltf['model.gltf']) > 0

                glb = s.export(file_type='glb')
                assert len(glb) > 0
                assert isinstance(glb, bytes)

                for export_format in ['dict', 'dict64']:
                    # try exporting the scene as a dict
                    # then make sure json can serialize it
                    e = g.json.dumps(s.export(file_type=export_format))

                    # reconstitute the dict into a scene
                    r = g.trimesh.load(g.json.loads(e))

                    # make sure the extents are similar before and after
                    assert g.np.allclose(g.np.product(s.extents),
                                         g.np.product(r.extents))

                s.rezero()
                assert (g.np.abs(s.centroid) < 1e-3).all()

                # make sure explode doesn't crash
                s.explode()

    def test_scaling(self):
        """
        Test the scaling of scenes including unit conversion.
        """
        scene = g.get_mesh('cycloidal.3DXML')

        md5 = scene.md5()
        extents = scene.bounding_box_oriented.primitive.extents.copy()

        # TODO: have OBB return sorted extents
        # and adjust the transform to be correct

        factor = 10.0
        scaled = scene.scaled(factor)

        # the oriented bounding box should scale exactly
        # with the scaling factor
        assert g.np.allclose(
            scaled.bounding_box_oriented.primitive.extents /
            extents,
            factor)

        # check bounding primitives
        assert scene.bounding_box.volume > 0.0
        assert scene.bounding_primitive.volume > 0.0

        # we shouldn't have modified the original scene
        assert scene.md5() == md5
        assert scaled.md5() != md5

        # 3DXML comes in as mm
        assert all(m.units == 'mm'
                   for m in scene.geometry.values())
        assert scene.units == 'mm'

        converted = scene.convert_units('in')

        assert g.np.allclose(
            converted.bounding_box_oriented.primitive.extents / extents,
            1.0 / 25.4,
            atol=1e-3)

        # shouldn't have changed the original extents
        assert g.np.allclose(
            extents,
            scene.bounding_box_oriented.primitive.extents)

        # original shouldn't have changed
        assert converted.units == 'in'
        assert all(m.units == 'in' for m in converted.geometry.values())

        assert scene.units == 'mm'

        # we shouldn't have modified the original scene
        assert scene.md5() == md5
        assert converted.md5() != md5

    def test_add_geometry(self):
        # list-typed geometry should create multiple nodes,
        # e.g., below code is equivalent to
        #     scene.add_geometry(geometry[0], node_name='voxels')
        #     scene.add_geometry(geometry[1], parent_node_name='voxels')
        scene = g.trimesh.Scene()
        geometry = [g.trimesh.creation.box(), g.trimesh.creation.box()]
        scene.add_geometry(geometry, node_name='voxels')
        assert len(scene.graph.nodes_geometry) == 2

    def test_add_concat(self):
        # create a scene with just a box in it
        a = g.trimesh.creation.box().scene()
        # do the same but move the box first
        b = g.trimesh.creation.box().apply_translation([2, 2, 2]).scene()
        # add the second scene to the first
        a.add_geometry(b)
        assert len(b.geometry) == 1
        assert len(a.geometry) == 2
        assert len(a.graph.nodes_geometry) == 2

    def test_delete(self):
        # check to make sure our geometry delete cleans up
        a = g.trimesh.creation.icosphere()
        b = g.trimesh.creation.icosphere().apply_translation([2, 0, 0])
        s = g.trimesh.Scene({'a': a, 'b': b})

        assert len(s.geometry) == 2
        assert len(s.graph.nodes_geometry) == 2
        # make sure every node has a transform
        [s.graph[n] for n in s.graph.nodes]

        # delete a geometry
        s.delete_geometry('a')
        assert len(s.geometry) == 1
        assert len(s.graph.nodes_geometry) == 1
        # if we screwed up the delete this will crash
        [s.graph[n] for n in s.graph.nodes]

    def test_dupe(self):
        m = g.get_mesh('tube.obj')

        assert m.body_count == 1

        s = g.trimesh.scene.split_scene(m)
        assert len(s.graph.nodes) == 2
        assert len(s.graph.nodes_geometry) == 1
        assert len(s.duplicate_nodes) == 1
        assert len(s.duplicate_nodes[0]) == 1

        c = s.copy()
        assert len(c.graph.nodes) == 2
        assert len(c.graph.nodes_geometry) == 1
        assert len(c.duplicate_nodes) == 1
        assert len(c.duplicate_nodes[0]) == 1

        u = s.convert_units('in', guess=True)
        assert len(u.graph.nodes_geometry) == 1
        assert len(u.duplicate_nodes) == 1
        assert len(u.duplicate_nodes[0]) == 1

    def test_dedupe(self):
        # create a scene with two identical meshes
        a = g.trimesh.creation.box()
        b = g.trimesh.creation.box().apply_translation([2, 2, 2])
        s = g.trimesh.Scene([a, b])

        # should have 2 geometries
        assert len(s.geometry) == 2
        assert len(s.graph.nodes_geometry) == 2

        # get a de-duplicated scene
        d = s.deduplicated()
        # should not have mutated original
        assert len(s.geometry) == 2
        assert len(s.graph.nodes_geometry) == 2
        # should only have one geometry
        assert len(d.geometry) == 1
        assert len(d.graph.nodes_geometry) == 1

    def test_3DXML(self):
        s = g.get_mesh('rod.3DXML')
        assert len(s.geometry) == 3
        assert len(s.graph.nodes_geometry) == 29

    def test_tri(self):
        scene = g.get_mesh('cycloidal.3DXML')

        # scene should have triangles
        assert g.trimesh.util.is_shape(scene.triangles, (-1, 3, 3))
        assert len(scene.triangles_node) == len(scene.triangles)

        # node name of inserted 2D geometry
        node = scene.add_geometry(g.get_mesh('2D/wrench.dxf'))
        # should be in the graph
        assert node in scene.graph.nodes
        # should have geometry defined
        assert node in scene.graph.nodes_geometry

        # 2D geometry has no triangles
        assert node not in scene.triangles_node
        # every geometry node except the one 2D thing
        # we inserted should be in triangles_node
        assert len(set(scene.triangles_node)) == len(
            scene.graph.nodes_geometry) - 1

    def test_empty(self):
        m = g.get_mesh('bunny.ply')

        # not watertight so will result in empty scene
        s = g.trimesh.scene.split_scene(m)
        assert len(s.geometry) == 0

        s = s.convert_units('inches')
        n = s.duplicate_nodes
        assert len(n) == 0

    def test_zipped(self):
        """
        Make sure a zip file with multiple file types
        is returned as a single scene.
        """
        # allow mixed 2D and 3D geometry
        m = g.get_mesh('scenes.zip', mixed=True)

        assert len(m.geometry) >= 6
        assert len(m.graph.nodes_geometry) >= 10
        assert any(isinstance(i, g.trimesh.path.Path2D)
                   for i in m.geometry.values())
        assert any(isinstance(i, g.trimesh.Trimesh)
                   for i in m.geometry.values())

        m = g.get_mesh('scenes.zip', mixed=False)
        assert len(m.geometry) < 6

    def test_doubling(self):
        s = g.get_mesh('cycloidal.3DXML')

        # make sure we parked our car where we thought
        assert len(s.geometry) == 13

        # concatenate a scene with itself
        r = s + s

        # new scene should have twice as much geometry
        assert len(r.geometry) == (2 * len(s.geometry))

        assert g.np.allclose(s.extents,
                             r.extents)

        # duplicate node groups should be twice as long
        set_ori = set([len(i) * 2 for i in s.duplicate_nodes])
        set_dbl = set([len(i) for i in r.duplicate_nodes])
        assert set_ori == set_dbl

    def test_empty_scene(self):
        # test an empty scene
        empty = g.trimesh.Trimesh([], [])
        assert empty.bounds is None
        assert empty.extents is None
        assert g.np.isclose(empty.scale, 1.0)

        # create a sphere
        sphere = g.trimesh.creation.icosphere()

        # empty scene should have None for bounds
        scene = empty.scene()
        assert scene.bounds is None

        # add a sphere to the empty scene
        scene.add_geometry(sphere)
        # bounds should now be populated
        assert scene.bounds.shape == (2, 3)
        assert g.np.allclose(scene.bounds, sphere.bounds)

    def test_transform(self):
        # check transforming scenes
        scene = g.trimesh.creation.box()
        assert g.np.allclose(scene.bounds, [[-.5, -.5, -.5], [.5, .5, .5]])

        scene.apply_translation([1, 0, 1])
        assert g.np.allclose(scene.bounds, [[.5, -.5, .5], [1.5, .5, 1.5]])


class GraphTests(g.unittest.TestCase):

    def test_forest(self):
        g = EnforcedForest(assert_forest=True)
        for i in range(5000):
            g.add_edge(random_chr(), random_chr())

    def test_cache(self):
        for i in range(10):
            scene = g.trimesh.Scene()
            scene.add_geometry(g.trimesh.creation.box())

            scene.set_camera()
            assert not g.np.allclose(
                scene.camera_transform,
                g.np.eye(4))
            scene.camera_transform = g.np.eye(4)
            assert g.np.allclose(
                scene.camera_transform,
                g.np.eye(4))


if __name__ == '__main__':
    g.trimesh.util.attach_to_log()
    g.unittest.main()
