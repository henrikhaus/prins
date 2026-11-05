import json
P = {
 "stack": {"art":"stack","lines":["DEPLOY","BLOCKED"],"sub":"APPROVE THE MIGRATION"},
 "moon": {"art":"moon","head":"Good night","sub":"LAPTOP OFF 23:00"},
 "bauhaus": {"art":"collide","big":"14","head":"COFFEE","sub":":00 WITH IDA"},
 "relief": {"art":"relief","word":"FOCUS","sub":"14:00 - 16:00 DO NOT DISTURB"},
 "extrude": {"art":"extrude","word":"SHIP IT"},
 "ransom": {"art":"ransom","lines":["CALL","SAM","BACK"]},
 "giant": {"art":"giant","big":"3","head":"days","sub":"to launch","foot":"MONDAY 9 NOV"},
 "mirror": {"art":"scene","scene":"mirror-ball","head":"DEMO DAY"},
 "rain": {"art":"rain","head":"RAIN AT 16","sub":"TAKE A JACKET","from":12,"mm":[0,0,0,0,.2,.6,1,.8,.4]},
 "ridges": {"art":"ridges","big":"147","sub":"COMMITS THIS WEEK","data":[12,31,18,44,27,9,6]},
 "merged": {"art":"merge","a":"main","b":"fix/auth-timeout","n":"#418","stat":"+1,204 -388"},
 "ticket": {"art":"ticket","to":"MARIA","at":"15:30","gate":"ROOM 4","qr":"https://meet.example/maria"},
 "airmail": {"art":"post","head":"Happy birthday","to":"Sam","icon":"candle"},
 "truchet": {"art":"cover","head":"THURSDAY","sub":"3 THINGS - 5 NOV"},
}
base = json.load(open('baseline.json'))
b = {k: len(json.dumps(v, separators=(",",":"))) for k,v in base.items()}
print("haiku", b, "mean", sum(b.values())/3)
s = {k: len(json.dumps(v, separators=(",",":"))) for k,v in P.items()}
print(s, "mean", round(sum(s.values())/len(s)), "max", max(s.values()))
print({k: json.dumps(v, separators=(",",":")) for k,v in P.items()}["stack"])
json.dump({k: json.dumps(v, separators=(",",":")) for k,v in P.items()}, open('out/payloads.json','w'))
