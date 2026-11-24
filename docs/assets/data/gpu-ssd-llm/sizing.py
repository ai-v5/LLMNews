#!/usr/bin/env python3
"""Reproduce illustrative LLM storage sizing numbers. Decimal GB/TB, binary KiB/GiB."""
import csv
import sys

GB,TB,KiB,GiB = 10**9,10**12,1024,1024**3
DAY=86400
rows=[]
def put(case, metric, n, unit):
    rows.append((case,metric,format(n,'.9g'),unit))

put("text_dataset","unique_read_at_12.2M_tok_s_int32",12.2e6*4/1e6,"MB/s")
put("text_dataset","size_at_200T_tok_int32",200e12*4/TB,"TB")

s=10e12*(2+4)
hosts=128
node=s/hosts
node_bw=2*7*.7
drives=2*15.36
write_day=node*DAY/300/TB
put("checkpoint","snapshot",s/TB,"TB")
put("checkpoint","bytes_per_node",node/GB,"GB")
put("checkpoint","local_flush_at_70pct_peak",node/(node_bw*GB),"s")
put("checkpoint","shared_write_average_every_5min",s/GB/300,"GB/s")
put("checkpoint","shared_write_to_finish_in_60s",s/GB/60,"GB/s")
put("checkpoint","two_local_versions",2*node/TB,"TB")
put("checkpoint","local_host_writes_every_5min",write_day,"TB/day/node")
put("checkpoint","local_host_DWPD_every_5min",write_day/drives,"DWPD")
put("checkpoint","local_host_DWPD_every_hour",write_day/12/drives,"DWPD")

ds_bytes_per_tok=890
prefix=128*KiB
event=100
restore=ds_bytes_per_tok*prefix
bw=event*restore*1.3
for k in (4,128,1024):
    put("kv","ssd_read_iops_at_%s_KiB"%k,bw/(k*KiB),"IOPS")
put("kv","ds_prefix_bytes",restore/1e6,"MB")
put("kv","aggregate_16_prefix_restore_in_25ms_with_amp",16*restore*1.3/.025/GB,"GB/s")
put("kv","ds_unique_reads",event*restore/GB,"GB/s")
put("kv","ds_reads_with_1.3x",bw/GB,"GB/s")
put("kv","ds_solo_restore_at_20GB_s",restore/(20*GB)*1e3,"ms")
gqa=2*80*8*128*2
put("kv","gqa_70b_prefix",prefix*gqa/GiB,"GiB")
put("kv","gqa_70b_solo_restore_at_20GB_s",prefix*gqa/(20*GB),"s")
write=event*8*KiB*ds_bytes_per_tok
day_tb=write*DAY/TB
put("kv","unique_write",write/GB,"GB/s")
put("kv","logical_writes",day_tb,"TB/day")
put("kv","raw_3day_EC10_2_watermark80",day_tb*3*1.2/.8,"TB")

w=70e9*2-64*GB
put("weights","non_HBM_bytes_per_step",w/GB,"GB")
put("weights","step_min_time_one_14GB_s_drive",w/(14*GB),"s")
put("weights","max_tok_s_at_63GB_s",63*GB/w,"tok/s")
put("weights","required_20_tok_s",w*20/TB,"TB/s")

o=70e9*12/64*8/GB
put("adam","read_and_write_each",o,"GB/step/node")
put("adam","min_overlap",max(o/50,o/25),"s")
put("adam","min_serial",o/50+o/25,"s")
put("adam","host_writes_10s_step",o*DAY/10/1000,"TB/day/node")
put("adam","host_DWPD_10s_step",o*DAY/10/1000/(8*3.84),"DWPD")

out=csv.writer(sys.stdout,lineterminator="\n")
out.writerow(("case","metric","value","unit"))
out.writerows(rows)
