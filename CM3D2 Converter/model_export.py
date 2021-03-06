import bpy, re, struct, mathutils, bmesh

def ArrangeName(name):
	name = re.sub(r'\.\d{3}$', "", name)
	return name

def WriteStr(file, s):
	str_count = len(s.encode('utf-8'))
	if 128 <= str_count:
		b = (str_count % 128) + 128
		file.write(struct.pack('<B', b))
		b = str_count // 128
		file.write(struct.pack('<B', b))
	else:
		file.write(struct.pack('<B', str_count))
	file.write(s.encode('utf-8'))

# メインオペレーター
class export_cm3d2_model(bpy.types.Operator):
	bl_idname = "export_mesh.export_cm3d2_model"
	bl_label = "CM3D2 Model (.model)"
	bl_description = "カスタムメイド3D2のmodelファイルを書き出します"
	bl_options = {'REGISTER'}
	
	filepath = bpy.props.StringProperty(subtype='FILE_PATH')
	filename_ext = ".model"
	filter_glob = bpy.props.StringProperty(default="*.model", options={'HIDDEN'})
	
	def invoke(self, context, event):
		# データの成否チェック
		ob = context.active_object
		if not ob:
			self.report(type={'ERROR'}, message="アクティブオブジェクトがありません")
			return {'CANCELLED'}
		if ob.type != 'MESH':
			self.report(type={'ERROR'}, message="メッシュオブジェクトを選択した状態で実行してください")
			return {'CANCELLED'}
		if not ob.active_material:
			self.report(type={'ERROR'}, message="マテリアルがありません")
			return {'CANCELLED'}
		for slot in ob.material_slots:
			if not slot:
				self.report(type={'ERROR'}, message="空のマテリアルスロットがあります")
				return {'CANCELLED'}
			try:
				slot.material['shader1']
				slot.material['shader2']
			except KeyError:
				self.report(type={'ERROR'}, message="マテリアルに「shader1」と「shader2」という名前のカスタムプロパティを用意してください")
				return {'CANCELLED'}
		me = ob.data
		if not me.uv_layers.active:
			self.report(type={'ERROR'}, message="UVがありません")
			return {'CANCELLED'}
		ob_names = ArrangeName(ob.name).split('.')
		if len(ob_names) != 2:
			self.report(type={'ERROR'}, message="オブジェクト名は「○○○.○○○」という形式にしてください")
			return {'CANCELLED'}
		
		if "BoneData" not in context.blend_data.texts.keys():
			self.report(type={'ERROR'}, message="テキスト「BoneData」が見つかりません、中止します")
			return {'CANCELLED'}
		if "LocalBoneData" not in context.blend_data.texts.keys():
			self.report(type={'ERROR'}, message="テキスト「LocalBoneData」が見つかりません、中止します")
			return {'CANCELLED'}
		
		self.filepath = context.user_preferences.addons[__name__.split('.')[0]].preferences.model_export_path
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}
	
	def execute(self, context):
		context.user_preferences.addons[__name__.split('.')[0]].preferences.model_export_path = self.filepath
		
		ob = context.active_object
		me = ob.data
		
		# BoneData情報読み込み
		bone_data = []
		for line in context.blend_data.texts["BoneData"].lines:
			data = line.body.split(',')
			if len(data) == 5:
				bone_data.append({})
				bone_data[-1]['name'] = data[0]
				bone_data[-1]['unknown'] = int(data[1])
				bone_data[-1]['parent_index'] = int(data[2])
				bone_data[-1]['co'] = []
				floats = data[3].split(' ')
				for f in floats:
					bone_data[-1]['co'].append(float(f))
				bone_data[-1]['rot'] = []
				floats = data[4].split(' ')
				for f in floats:
					bone_data[-1]['rot'].append(float(f))
		if len(bone_data) <= 0:
			self.report(type={'ERROR'}, message="テキスト「BoneData」に有効なデータがありません")
			return {'CANCELLED'}
		
		# LocalBoneData情報読み込み
		local_bone_data = []
		local_bone_names = []
		for line in context.blend_data.texts["LocalBoneData"].lines:
			data = line.body.split(',')
			if len(data) == 2:
				local_bone_data.append({})
				local_bone_data[-1]['name'] = data[0]
				local_bone_data[-1]['matrix'] = []
				floats = data[1].split(' ')
				for f in floats:
					local_bone_data[-1]['matrix'].append(float(f))
				local_bone_names.append(data[0])
		if len(local_bone_data) <= 0:
			self.report(type={'ERROR'}, message="テキスト「LocalBoneData」に有効なデータがありません")
			return {'CANCELLED'}
		
		# ファイル先頭
		file = open(self.filepath, 'wb')
		
		WriteStr(file, 'CM3D2_MESH')
		file.write(struct.pack('<i', 1000))
		
		ob_names = ArrangeName(ob.name).split('.')
		WriteStr(file, ob_names[0])
		WriteStr(file, ob_names[1])
		
		# ボーン情報書き出し
		file.write(struct.pack('<i', len(bone_data)))
		for bone in bone_data:
			WriteStr(file, bone['name'])
			file.write(struct.pack('<b', bone['unknown']))
		for bone in bone_data:
			file.write(struct.pack('<i', bone['parent_index']))
		for bone in bone_data:
			file.write(struct.pack('<3f', bone['co'][0], bone['co'][1], bone['co'][2]))
			file.write(struct.pack('<4f', bone['rot'][0], bone['rot'][1], bone['rot'][2], bone['rot'][3]))
		
		# 正しい頂点数などを取得
		bm = bmesh.new()
		bm.from_mesh(me)
		uv_lay = bm.loops.layers.uv.active
		vert_uvs = []
		vert_iuv = []
		vert_count = 0
		for vert in bm.verts:
			vert_uvs.append([])
			for loop in vert.link_loops:
				uv = loop[uv_lay].uv
				if uv not in vert_uvs[-1]:
					vert_uvs[-1].append(uv)
					vert_iuv.append((vert.index, uv.x, uv.y))
					vert_count += 1
		
		file.write(struct.pack('<2i', vert_count, len(ob.material_slots)))
		
		# ローカルボーン情報を書き出し
		file.write(struct.pack('<i', len(local_bone_data)))
		for bone in local_bone_data:
			WriteStr(file, bone['name'])
		for bone in local_bone_data:
			for f in bone['matrix']:
				file.write(struct.pack('<f', f))
		
		# 頂点情報を書き出し
		for i, vert in enumerate(bm.verts):
			for uv in vert_uvs[i]:
				co = vert.co.copy()
				file.write(struct.pack('<3f', -co.x, co.y, co.z))
				no = vert.normal.copy()
				file.write(struct.pack('<3f', -no.x, no.y, no.z))
				file.write(struct.pack('<2f', uv.x, uv.y))
		# ウェイト情報を書き出し
		file.write(struct.pack('<i', 0))
		for vert in me.vertices:
			for uv in vert_uvs[vert.index]:
				vgs = []
				for vg in vert.groups:
					name = ob.vertex_groups[vg.group].name
					if name not in local_bone_names:
						continue
					weight = vg.weight
					vgs.append((name, weight))
				vgs.sort(key=lambda vg: vg[1])
				vgs.reverse()
				for i in range(4):
					try:
						name = vgs[i][0]
					except IndexError:
						index = 0
					else:
						index = 0
						for i, bone in enumerate(local_bone_data):
							if bone['name'] == name:
								break
							index += 1
						else:
							index = 0
					file.write(struct.pack('<h', index))
				for i in range(4):
					try:
						weight = vgs[i][1]
					except IndexError:
						weight = 0
					file.write(struct.pack('<f', weight))
		
		# 面情報を書き出し
		error_face_count = 0
		for mate_index, slot in enumerate(ob.material_slots):
			face_count = 0
			faces = []
			for face in bm.faces:
				if len(face.verts) != 3:
					error_face_count += 1
					continue
				if face.material_index != mate_index:
					continue
				for loop in face.loops:
					uv = loop[uv_lay].uv
					index = loop.vert.index
					vert_index = vert_iuv.index((index, uv.x, uv.y))
					faces.append(vert_index)
				face_count += 1
			file.write(struct.pack('<i', face_count * 3))
			for face in faces:
				file.write(struct.pack('<h', face))
		if 1 <= error_face_count:
			self.report(type={'INFO'}, message="多角ポリゴンが%dつ見つかりました、正常に出力できなかった可能性があります" % error_face_count)
		
		# マテリアルを書き出し
		file.write(struct.pack('<i', len(ob.material_slots)))
		for slot_index, slot in enumerate(ob.material_slots):
			mate = slot.material
			WriteStr(file, ArrangeName(mate.name))
			WriteStr(file, mate['shader1'])
			WriteStr(file, mate['shader2'])
			for tindex, tslot in enumerate(mate.texture_slots):
				if not tslot:
					continue
				tex = tslot.texture
				if mate.use_textures[tindex]:
					WriteStr(file, 'tex')
					WriteStr(file, ArrangeName(tex.name))
					if tex.image:
						img = tex.image
						WriteStr(file, 'tex2d')
						WriteStr(file, ArrangeName(img.name))
						path = img.filepath
						path = path.replace('//..\\..\\Assets\\', 'Assets/')
						path = path.replace('\\', '/')
						WriteStr(file, path)
						col = tslot.color
						file.write(struct.pack('<3f', col[0], col[1], col[2]))
						file.write(struct.pack('<f', tslot.diffuse_color_factor))
					else:
						WriteStr(file, 'null')
				else:
					if tslot.use_rgb_to_intensity:
						WriteStr(file, 'col')
						WriteStr(file, ArrangeName(tex.name))
						col = tslot.color
						file.write(struct.pack('<3f', col[0], col[1], col[2]))
						file.write(struct.pack('<f', tslot.diffuse_color_factor))
					else:
						WriteStr(file, 'f')
						WriteStr(file, ArrangeName(tex.name))
						file.write(struct.pack('<f', tslot.diffuse_color_factor))
			WriteStr(file, 'end')
		
		# モーフを書き出し
		if 2 <= len(me.shape_keys.key_blocks):
			for shape_key in me.shape_keys.key_blocks[1:]:
				WriteStr(file, 'morph')
				WriteStr(file, shape_key.name)
				morph = []
				vert_index = 0
				for i, vert in enumerate(me.vertices):
					for d in vert_uvs[i]:
						if shape_key.data[i].co != vert.co:
							morph.append((vert_index, shape_key.data[i].co - vert.co))
						vert_index += 1
				file.write(struct.pack('<i', len(morph)))
				for index, vec in morph:
					file.write(struct.pack('<h', index))
					file.write(struct.pack('<3f', vec.x, vec.y, vec.z))
					file.write(struct.pack('<3f', 0, 0, 0))
		WriteStr(file, 'end')
		
		return {'FINISHED'}

# メニューを登録する関数
def menu_func(self, context):
	self.layout.operator(export_cm3d2_model.bl_idname, icon='PLUGIN')
