import json,tempfile,unittest,struct
from pathlib import Path
from subtitle_formats import Document,Cue,scale_ass
from subtitle_mapping import TimingMap,Section,fit_map,text_anchors
from subtitle_sync import retime_sup,speech_anchors,parser,run

class SubtitleTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def file(self,name,text):p=self.root/name;p.write_text(text,encoding='utf-8');return p
 def mapping(self,scale=1,offset=2,evidence='visual'):return TimingMap([Section(0,1000,scale,offset,[])],evidence)
 def test_srt_multiple_cues_preserve_arabic_and_markup(self):
  src=self.file('in.srt','1\n00:00:01,000 --> 00:00:02,000\n<b>مرحبا</b>\n\n2\n00:00:04,000 --> 00:00:06,000\nSecond line\n')
  d=Document(src);self.assertEqual(len(d.cues),2);out=self.root/'out.srt';d.write(out,self.mapping());s=out.read_text();self.assertIn('00:00:03,000 --> 00:00:04,000',s);self.assertIn('<b>مرحبا</b>',s);self.assertIn('00:00:06,000 --> 00:00:08,000',s)
 def test_ass_preserves_headers_styles_drawings_fonts_and_scales_animation(self):
  s='[Script Info]\nPlayResX: 640\n[V4+ Styles]\nStyle: Sign,Arial,30\n[Fonts]\nfontname: test\nABCxyz\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 3,0:00:01.00,0:00:05.00,Sign,,0,0,0,,{\\move(1,2,3,4,0,1000)\\t(0,1000,2,\\clip(1,2,3,4))\\fad(100,200)\\k20}Text\n'
  src=self.file('in.ass',s);out=self.root/'out.ass';d=Document(src);report=d.write(out,self.mapping(2));text=out.read_text();self.assertIn('0:00:04.00,0:00:12.00',text);self.assertIn(r'\move(1,2,3,4,0,2000)',text);self.assertIn(r'\t(0,2000,2,\clip(1,2,3,4))',text);self.assertIn(r'\fad(200,400)\k40',text);self.assertEqual(s.split('[Events]')[0],text.split('[Events]')[0]);self.assertEqual(report[0]['status'],'mapped')
 def test_ass_fade_karaoke_and_implicit_transforms(self):
  s=r'{\fade(255,0,255,0,100,200,300)\kt30\ko10\t(2,\fscx120)\pos(50,60)}'
  out=scale_ass(s,2);self.assertIn(r'\fade(255,0,255,0,200,400,600)',out);self.assertIn(r'\kt60\ko20',out);self.assertIn(r'\t(2,\fscx120)',out);self.assertIn(r'\pos(50,60)',out)
 def test_karaoke_rounding_does_not_accumulate(self):
  import re
  result=scale_ass(r'{\k1}a{\k1}b{\k1}c{\k1}d',1.25)
  self.assertEqual(sum(map(int,re.findall(r'\\k(\d+)',result))),5)
 def test_typeset_without_visual_evidence_is_flagged(self):
  s=self.file('in.ass','[Events]\nFormat: Layer, Start, End, Style, Text\nDialogue: 0,0:00:01.00,0:00:02.00,Sign,{\\pos(1,2)}Hello\n');d=Document(s);report=d.write(self.root/'o.ass',self.mapping(evidence='speech'));self.assertEqual(report[0]['status'],'review')
 def test_unmapped_cut_cue_keeps_original_and_is_reported(self):
  src=self.file('in.srt','1\n00:00:09,000 --> 00:00:12,000\nCrosses cut\n');d=Document(src);m=TimingMap([Section(0,10,1,0,[]),Section(11,30,1,1,[])]);out=self.root/'o.srt';report=d.write(out,m);self.assertEqual(report[0]['status'],'unmapped');self.assertEqual(src.read_bytes(),out.read_bytes())
 def test_vtt_styles_settings_and_inline_timestamps_preserved(self):
  s='WEBVTT\n\nSTYLE\n::cue { color: lime; }\n\ncue-id\n00:01.000 --> 00:03.000 align:start position:20%\nHello <00:02.000>world\n';src=self.file('x.vtt',s);out=self.root/'o.vtt';Document(src).write(out,self.mapping());text=out.read_text();self.assertIn('::cue { color: lime; }',text);self.assertIn('align:start position:20%',text);self.assertIn('<00:00:04.000>',text)
 def test_ttml_style_preservation_and_nested_rejection(self):
  src=self.file('x.ttml','<tt><head><styling id="keep"/></head><body><p begin="1s" end="3s" style="a"><span>Hi</span></p></body></tt>');out=self.root/'o.ttml';Document(src).write(out,self.mapping());self.assertIn('begin="3.000s"',out.read_text());self.assertIn('<styling id="keep"/>',out.read_text());bad=self.file('bad.ttml','<tt><body begin="2s"><p begin="1s" end="3s">Hi</p></body></tt>');self.assertRaises(ValueError,Document,bad)
 def test_microdvd_and_mpl2(self):
  src=self.file('x.sub','{25}{50}Hello|world\n');out=self.root/'o.sub';Document(src,fps=25).write(out,self.mapping(),target_fps=24);self.assertEqual(out.read_text(),'{72}{96}Hello|world\n');self.assertRaises(ValueError,Document,src)
  src=self.file('x.mpl2','[10][20]Hello\n');Document(src).write(out,self.mapping());self.assertEqual(out.read_text(),'[30][40]Hello\n')
 def test_sami(self):
  src=self.file('x.smi','<SAMI><STYLE>.a {color:red}</STYLE><SYNC Start=1000><P>Hi<SYNC Start=3000><P>&nbsp;</SAMI>');out=self.root/'o.smi';Document(src).write(out,self.mapping());self.assertIn('Start=3000',out.read_text());self.assertIn('Start=5000',out.read_text())
 def test_map_cut_and_rate(self):
  rows=[(x,1.04*x+2,.99) for x in range(10,100,10)]+[(x,1.04*x-30,.99) for x in range(150,240,10)]
  m=fit_map(rows,260,'visual',.25);self.assertEqual(len(m.sections),2);self.assertAlmostEqual(m.interval(50,55)[0],54,places=4);self.assertIsNone(m.interval(100,150));self.assertAlmostEqual(m.interval(180,185)[0],157.2,places=4)
 def test_text_matches_reject_repeated_phrases(self):
  a=[Cue(i*10,i*10+3,t,()) for i,t in enumerate(['The blue bird flew over the river','We should return before sunset','I left the book beside the window','Please open the door for our guest','My mother is waiting in the garden'])];b=[Cue(c.start+7,c.end+7,c.text,()) for c in a];rows=text_anchors(a,b);self.assertEqual(len(rows),5);m=fit_map(rows,50);self.assertAlmostEqual(m.interval(20,23)[0],27)
 def test_speech_word_windows(self):
  c=Cue(1,4,'Please open the door',());words=[{'text':w,'start':10+i,'end':10+i+.5,'probability':.99} for i,w in enumerate('Please open the door'.split())];r=speech_anchors([c],words);self.assertEqual(len(r),1);self.assertEqual(r[0][1],11.75)
 def test_sup_payload_preserved(self):
  payload=struct.pack('>HHBHBBBB',1920,1080,0x10,0,0,0,0,0);data=b'PG'+struct.pack('>II',90000,0)+b'\x16'+struct.pack('>H',len(payload))+payload;p=self.root/'x.sup';p.write_bytes(data);o=self.root/'o.sup';retime_sup(p,o,self.mapping());self.assertEqual(struct.unpack_from('>I',o.read_bytes(),2)[0],270000);self.assertEqual(o.read_bytes()[10:],data[10:])
 def test_imported_audio_map_direction(self):
  p=self.file('plan.json',json.dumps({'segments':[{'kind':'audio','source_start':10,'target_start':0,'target_end':20,'speed':2}]}));m=TimingMap.load(p);self.assertEqual(m.interval(12,14)[:3],(1,2,.5))
 def test_reference_end_to_end_and_no_overwrite(self):
  texts=['A different long sentence here','The moon shines above the forest','Why are you standing beside the river','Tomorrow we will visit our old teacher','Bring the red book to the station']
  def srt(shift):
   from subtitle_formats import timestamp
   return '\n\n'.join(f'{i+1}\n{timestamp(i*10+shift)} --> {timestamp(i*10+3+shift)}\n{t}' for i,t in enumerate(texts))
  a=self.file('a.srt',srt(0));b=self.file('b.srt',srt(5));out=self.root/'result';args=parser().parse_args(['--subtitle',str(a),'--reference-subtitle',str(b),'--out',str(out)]);self.assertEqual(run(args),0);self.assertTrue((out/'synced.srt').exists());self.assertRaises(ValueError,run,args)

if __name__=='__main__':unittest.main()
