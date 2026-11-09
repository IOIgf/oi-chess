"""生成含 O2、SPFA、减速、延迟与换攻状态的真实特效演示。"""
import make_demo as D
from pathlib import Path
D.OUT=str(Path(D.ROOT)/'特效预览.html')
D.A_BOARD=[('spfa',3,0),('o2',3,1),('expectation',2,1),('bitmask_dp',4,1),('gcd',2,0),('tree_array',4,0),('cdq',5,1),('merge_sort',2,2)]
D.B_BOARD=[('bfs',3,0),('diff',2,1),('inverse',4,0),('quick_sort',5,1),('xor',2,2),('sweep_line',4,2),('segment_tree',5,0),('fermat',1,1)]
D.SRV.random.seed(20261117)
D.main()
