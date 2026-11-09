from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=(root/'server.py').read_text().replace('PORT = 8080','PORT = 8096').replace('PREP_TIME = 30.0','PREP_TIME = 1.0').replace('BATTLE_TIME = 30.0','BATTLE_TIME = 3.0').replace('MAX_ROUNDS = 10','MAX_ROUNDS = 3')
s=s.replace("DATA_DIR = (Path(__file__).parent / 'data').resolve()", "DATA_DIR = (Path(__file__).parent / 'audit' / 'stress_data').resolve()")
exec(compile(s,'server.py','exec'),{'__file__':str(root/'server.py'),'__name__':'__main__'})
