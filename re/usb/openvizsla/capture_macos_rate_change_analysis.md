I have some other USB trace from same device, where I while the device is operational change the sample rate.  

I reduced the data set to the higher level packets using the python script, and manually stripped out the many repetitive 512 byte audio in/out packets, 
leaving the relevant packets exchanged around the sample rate, and a few sample data packets for timing reference.

Analyse these rate change operations, and derive exact handshake to be performed with the device to perform the rate change effectively. (additional context: in my current Linux driver I need to perform a usb reset to make the device reliably change rate; this is sub-optimal, and I want to learn from how the proprietary MacOS driver is doing this to see if I can do the rate change in a more elegant way).

```
Timestamp    | Direction  | Target   | Bytes | Payload Data
----------------------------------------------------------------------------------------------------
....
....
....
10.670974    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 04 .....
10.671106    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.671153    | IN         | 8.6      | 512   | 02 02 02 02 02 02 02 02 02 02 02 02 02 02 06 .....
10.671328    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.671338    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.671392    | IN         | 8.6      | 512   | 02 02 02 02 02 02 02 02 02 02 02 02 02 02 06 .....
10.671494    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.671573    | IN         | 8.6      | 512   | 03 03 03 03 03 03 03 03 03 03 03 03 03 03 07 .....
10.671713    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.671764    | IN         | 8.6      | 512   | 03 03 03 03 03 03 03 03 03 03 03 03 03 03 03 .....
10.822215    | SETUP      | 8.0      | 8     | 01 0b 00 00 01 00 00 00
10.822241    | IN         | 8.0      | 0     | []
10.823271    | SETUP      | 8.0      | 8     | 01 0b 00 00 00 00 00 00
10.823296    | IN         | 8.0      | 0     | []
10.823750    | SETUP      | 8.0      | 8     | 01 0b 01 00 00 00 00 00
10.823776    | IN         | 8.0      | 0     | []
10.823998    | SETUP      | 8.0      | 8     | 01 0b 01 00 01 00 00 00
10.824024    | IN         | 8.0      | 0     | []
10.824765    | SETUP      | 8.0      | 8     | 02 01 00 00 86 00 00 00
10.824790    | IN         | 8.0      | 0     | []
10.825963    | SETUP      | 8.0      | 8     | 02 01 00 00 05 00 00 00
10.825988    | IN         | 8.0      | 0     | []
10.826435    | SETUP      | 8.0      | 8     | 02 01 00 00 83 00 00 00
10.826460    | IN         | 8.0      | 0     | []
10.831739    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
10.831764    | IN         | 8.0      | 1     | 32
10.831770    | OUT        | 8.0      | 0     | []
10.831940    | SETUP      | 8.0      | 8     | a2 81 00 01 00 00 03 00
10.832049    | IN         | 8.0      | 3     | 44 ac 00
10.832054    | OUT        | 8.0      | 0     | []
10.883037    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
10.883068    | OUT        | 8.0      | 3     | 80 bb 00
10.883093    | IN         | 8.0      | 0     | []
10.893722    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
10.893758    | OUT        | 8.0      | 3     | 80 bb 00
10.893782    | IN         | 8.0      | 0     | []
10.893969    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
10.894000    | OUT        | 8.0      | 3     | 80 bb 00
10.894024    | IN         | 8.0      | 0     | []
10.894341    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
10.894372    | OUT        | 8.0      | 3     | 80 bb 00
10.894396    | IN         | 8.0      | 0     | []
10.894535    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
10.894567    | OUT        | 8.0      | 3     | 80 bb 00
10.894591    | IN         | 8.0      | 0     | []
10.894721    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
10.894758    | OUT        | 8.0      | 3     | 80 bb 00
10.894782    | IN         | 8.0      | 0     | []
10.894917    | SETUP      | 8.0      | 8     | a2 81 00 01 86 00 03 00
10.895026    | IN         | 8.0      | 3     | 80 bb 00
10.895031    | OUT        | 8.0      | 0     | []
10.945711    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
10.945736    | IN         | 8.0      | 1     | 32
10.945741    | OUT        | 8.0      | 0     | []
10.945911    | SETUP      | 8.0      | 8     | 40 49 32 00 00 00 00 00
10.946130    | IN         | 8.0      | 0     | []
10.946411    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.946421    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.948454    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.948517    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
10.948637    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
....
....
....
12.408386    | IN         | 8.6      | 512   | 03 03 03 03 03 03 03 03 03 03 03 03 03 03 03 .....
12.408594    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 04 .....
12.408632    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.408741    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.408839    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.559643    | SETUP      | 8.0      | 8     | 01 0b 00 00 01 00 00 00
12.559668    | IN         | 8.0      | 0     | []
12.560701    | SETUP      | 8.0      | 8     | 01 0b 00 00 00 00 00 00
12.560726    | IN         | 8.0      | 0     | []
12.561189    | SETUP      | 8.0      | 8     | 01 0b 01 00 00 00 00 00
12.561215    | IN         | 8.0      | 0     | []
12.561496    | SETUP      | 8.0      | 8     | 01 0b 01 00 01 00 00 00
12.561521    | IN         | 8.0      | 0     | []
12.562268    | SETUP      | 8.0      | 8     | 02 01 00 00 86 00 00 00
12.562293    | IN         | 8.0      | 0     | []
12.563428    | SETUP      | 8.0      | 8     | 02 01 00 00 05 00 00 00
12.563457    | IN         | 8.0      | 0     | []
12.563856    | SETUP      | 8.0      | 8     | 02 01 00 00 83 00 00 00
12.563882    | IN         | 8.0      | 0     | []
12.569441    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
12.569466    | IN         | 8.0      | 1     | 32
12.569472    | OUT        | 8.0      | 0     | []
12.569607    | SETUP      | 8.0      | 8     | a2 81 00 01 00 00 03 00
12.569715    | IN         | 8.0      | 3     | 80 bb 00
12.569721    | OUT        | 8.0      | 0     | []
12.620744    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
12.620773    | OUT        | 8.0      | 3     | 44 ac 00
12.620798    | IN         | 8.0      | 0     | []
12.631380    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
12.631411    | OUT        | 8.0      | 3     | 44 ac 00
12.631439    | IN         | 8.0      | 0     | []
12.631602    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
12.631633    | OUT        | 8.0      | 3     | 44 ac 00
12.631658    | IN         | 8.0      | 0     | []
12.631982    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
12.632014    | OUT        | 8.0      | 3     | 44 ac 00
12.632039    | IN         | 8.0      | 0     | []
12.632225    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
12.632256    | OUT        | 8.0      | 3     | 44 ac 00
12.632281    | IN         | 8.0      | 0     | []
12.632442    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
12.632472    | OUT        | 8.0      | 3     | 44 ac 00
12.632497    | IN         | 8.0      | 0     | []
12.632648    | SETUP      | 8.0      | 8     | a2 81 00 01 86 00 03 00
12.632778    | IN         | 8.0      | 3     | 44 ac 00
12.632783    | OUT        | 8.0      | 0     | []
12.683351    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
12.683376    | IN         | 8.0      | 1     | 32
12.683382    | OUT        | 8.0      | 0     | []
12.683560    | SETUP      | 8.0      | 8     | 40 49 32 00 00 00 00 00
12.683776    | IN         | 8.0      | 0     | []
12.683979    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.683988    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.703696    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.703735    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
12.703867    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
....
....
....
16.228031    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.228104    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 .....
16.228245    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 .....
16.228255    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.228367    | IN         | 8.6      | 512   | 05 05 05 05 05 05 05 05 05 05 05 05 05 05 .....
16.228453    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.228521    | IN         | 8.6      | 512   | 01 01 01 01 01 01 01 01 01 01 01 01 01 01 .....
16.228647    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.228679    | IN         | 8.6      | 512   | 06 06 06 06 06 06 06 06 06 06 06 06 06 06 .....
16.379605    | SETUP      | 8.0      | 8     | 01 0b 00 00 01 00 00 00
16.379630    | IN         | 8.0      | 0     | []
16.380570    | SETUP      | 8.0      | 8     | 01 0b 00 00 00 00 00 00
16.380595    | IN         | 8.0      | 0     | []
16.381090    | SETUP      | 8.0      | 8     | 01 0b 01 00 00 00 00 00
16.381115    | IN         | 8.0      | 0     | []
16.381423    | SETUP      | 8.0      | 8     | 01 0b 01 00 01 00 00 00
16.381448    | IN         | 8.0      | 0     | []
16.382249    | SETUP      | 8.0      | 8     | 02 01 00 00 86 00 00 00
16.382274    | IN         | 8.0      | 0     | []
16.383341    | SETUP      | 8.0      | 8     | 02 01 00 00 05 00 00 00
16.383366    | IN         | 8.0      | 0     | []
16.383795    | SETUP      | 8.0      | 8     | 02 01 00 00 83 00 00 00
16.383820    | IN         | 8.0      | 0     | []
16.389231    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
16.389256    | IN         | 8.0      | 1     | 32
16.389262    | OUT        | 8.0      | 0     | []
16.389403    | SETUP      | 8.0      | 8     | a2 81 00 01 00 00 03 00
16.389511    | IN         | 8.0      | 3     | 80 bb 00
16.389517    | OUT        | 8.0      | 0     | []
16.440666    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
16.440697    | OUT        | 8.0      | 3     | 88 58 01
16.440722    | IN         | 8.0      | 0     | []
16.451807    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
16.451838    | OUT        | 8.0      | 3     | 88 58 01
16.451860    | IN         | 8.0      | 0     | []
16.452057    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
16.452088    | OUT        | 8.0      | 3     | 88 58 01
16.452113    | IN         | 8.0      | 0     | []
16.452451    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
16.452485    | OUT        | 8.0      | 3     | 88 58 01
16.452511    | IN         | 8.0      | 0     | []
16.452694    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
16.452730    | OUT        | 8.0      | 3     | 88 58 01
16.452756    | IN         | 8.0      | 0     | []
16.452938    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
16.452968    | OUT        | 8.0      | 3     | 88 58 01
16.452994    | IN         | 8.0      | 0     | []
16.453184    | SETUP      | 8.0      | 8     | a2 81 00 01 86 00 03 00
16.453293    | IN         | 8.0      | 3     | 88 58 01
16.453298    | OUT        | 8.0      | 0     | []
16.503508    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
16.503533    | IN         | 8.0      | 1     | 32
16.503539    | OUT        | 8.0      | 0     | []
16.503680    | SETUP      | 8.0      | 8     | 40 49 32 00 00 00 00 00
16.503899    | IN         | 8.0      | 0     | []
16.504116    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.504126    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.512657    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
16.512667    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
....
....
....
17.614317    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.614369    | IN         | 8.6      | 512   | 06 06 06 06 06 06 06 06 06 06 06 06 06 06 .....
17.614428    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.614472    | IN         | 8.6      | 512   | 05 05 05 05 05 05 05 05 05 05 05 05 05 05 .....
17.614550    | IN         | 8.6      | 512   | 03 03 03 03 03 03 03 03 03 03 03 03 03 01 .....
17.614560    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.765546    | SETUP      | 8.0      | 8     | 01 0b 00 00 01 00 00 00
17.765571    | IN         | 8.0      | 0     | []
17.766523    | SETUP      | 8.0      | 8     | 01 0b 00 00 00 00 00 00
17.766548    | IN         | 8.0      | 0     | []
17.767048    | SETUP      | 8.0      | 8     | 01 0b 01 00 00 00 00 00
17.767073    | IN         | 8.0      | 0     | []
17.767376    | SETUP      | 8.0      | 8     | 01 0b 01 00 01 00 00 00
17.767401    | IN         | 8.0      | 0     | []
17.768202    | SETUP      | 8.0      | 8     | 02 01 00 00 86 00 00 00
17.768227    | IN         | 8.0      | 0     | []
17.769346    | SETUP      | 8.0      | 8     | 02 01 00 00 05 00 00 00
17.769371    | IN         | 8.0      | 0     | []
17.769830    | SETUP      | 8.0      | 8     | 02 01 00 00 83 00 00 00
17.769855    | IN         | 8.0      | 0     | []
17.775277    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
17.775302    | IN         | 8.0      | 1     | 32
17.775307    | OUT        | 8.0      | 0     | []
17.775456    | SETUP      | 8.0      | 8     | a2 81 00 01 00 00 03 00
17.775565    | IN         | 8.0      | 3     | 88 58 01
17.775570    | OUT        | 8.0      | 0     | []
17.825853    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
17.825885    | OUT        | 8.0      | 3     | 00 77 01
17.825910    | IN         | 8.0      | 0     | []
17.836637    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
17.836665    | OUT        | 8.0      | 3     | 00 77 01
17.836690    | IN         | 8.0      | 0     | []
17.836836    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
17.836867    | OUT        | 8.0      | 3     | 00 77 01
17.836897    | IN         | 8.0      | 0     | []
17.837170    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
17.837199    | OUT        | 8.0      | 3     | 00 77 01
17.837225    | IN         | 8.0      | 0     | []
17.837397    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
17.837427    | OUT        | 8.0      | 3     | 00 77 01
17.837450    | IN         | 8.0      | 0     | []
17.837624    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
17.837655    | OUT        | 8.0      | 3     | 00 77 01
17.837680    | IN         | 8.0      | 0     | []
17.837827    | SETUP      | 8.0      | 8     | a2 81 00 01 86 00 03 00
17.837918    | IN         | 8.0      | 3     | 00 77 01
17.837924    | OUT        | 8.0      | 0     | []
17.888360    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
17.888386    | IN         | 8.0      | 1     | 32
17.888391    | OUT        | 8.0      | 0     | []
17.888517    | SETUP      | 8.0      | 8     | 40 49 32 00 00 00 00 00
17.888735    | IN         | 8.0      | 0     | []
17.888938    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.888948    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.890426    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.890436    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.890507    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.890552    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
17.890607    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
....
....
....
19.161379    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.161447    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 02 .....
19.161492    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.161551    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 04 .....
19.161595    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.161627    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 04 .....
19.161690    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.312582    | SETUP      | 8.0      | 8     | 01 0b 00 00 01 00 00 00
19.312607    | IN         | 8.0      | 0     | []
19.313529    | SETUP      | 8.0      | 8     | 01 0b 00 00 00 00 00 00
19.313554    | IN         | 8.0      | 0     | []
19.314093    | SETUP      | 8.0      | 8     | 01 0b 01 00 00 00 00 00
19.314119    | IN         | 8.0      | 0     | []
19.314400    | SETUP      | 8.0      | 8     | 01 0b 01 00 01 00 00 00
19.314425    | IN         | 8.0      | 0     | []
19.315169    | SETUP      | 8.0      | 8     | 02 01 00 00 86 00 00 00
19.315194    | IN         | 8.0      | 0     | []
19.316280    | SETUP      | 8.0      | 8     | 02 01 00 00 05 00 00 00
19.316305    | IN         | 8.0      | 0     | []
19.316710    | SETUP      | 8.0      | 8     | 02 01 00 00 83 00 00 00
19.316735    | IN         | 8.0      | 0     | []
19.322344    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
19.322369    | IN         | 8.0      | 1     | 32
19.322375    | OUT        | 8.0      | 0     | []
19.322534    | SETUP      | 8.0      | 8     | a2 81 00 01 00 00 03 00
19.322643    | IN         | 8.0      | 3     | 00 77 01
19.322669    | OUT        | 8.0      | 0     | []
19.372894    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
19.372924    | OUT        | 8.0      | 3     | 44 ac 00
19.372947    | IN         | 8.0      | 0     | []
19.383843    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
19.383877    | OUT        | 8.0      | 3     | 44 ac 00
19.383901    | IN         | 8.0      | 0     | []
19.384091    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
19.384127    | OUT        | 8.0      | 3     | 44 ac 00
19.384153    | IN         | 8.0      | 0     | []
19.384527    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
19.384558    | OUT        | 8.0      | 3     | 44 ac 00
19.384583    | IN         | 8.0      | 0     | []
19.384747    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
19.384775    | OUT        | 8.0      | 3     | 44 ac 00
19.384801    | IN         | 8.0      | 0     | []
19.385043    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
19.385074    | OUT        | 8.0      | 3     | 44 ac 00
19.385099    | IN         | 8.0      | 0     | []
19.385240    | SETUP      | 8.0      | 8     | a2 81 00 01 86 00 03 00
19.385352    | IN         | 8.0      | 3     | 44 ac 00
19.385357    | OUT        | 8.0      | 0     | []
19.436209    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
19.436234    | IN         | 8.0      | 1     | 32
19.436240    | OUT        | 8.0      | 0     | []
19.436401    | SETUP      | 8.0      | 8     | 40 49 32 00 00 00 00 00
19.436615    | IN         | 8.0      | 0     | []
19.436893    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.436903    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.437720    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.437783    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
19.437903    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
....
....
....
20.676275    | IN         | 8.6      | 512   | 02 02 02 02 02 02 02 02 02 02 02 02 02 02 02 .....
20.676430    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
20.676476    | IN         | 8.6      | 512   | 06 06 06 06 06 06 06 06 06 06 06 06 06 06 06 .....
20.676650    | IN         | 8.6      | 512   | 04 04 04 04 04 04 04 04 04 04 04 04 04 04 04 .....
20.676659    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
20.827644    | SETUP      | 8.0      | 8     | 01 0b 00 00 01 00 00 00
20.827669    | IN         | 8.0      | 0     | []
20.828631    | SETUP      | 8.0      | 8     | 01 0b 00 00 00 00 00 00
20.828656    | IN         | 8.0      | 0     | []
20.829180    | SETUP      | 8.0      | 8     | 01 0b 01 00 00 00 00 00
20.829205    | IN         | 8.0      | 0     | []
20.829508    | SETUP      | 8.0      | 8     | 01 0b 01 00 01 00 00 00
20.829532    | IN         | 8.0      | 0     | []
20.830275    | SETUP      | 8.0      | 8     | 02 01 00 00 86 00 00 00
20.830303    | IN         | 8.0      | 0     | []
20.831407    | SETUP      | 8.0      | 8     | 02 01 00 00 05 00 00 00
20.831432    | IN         | 8.0      | 0     | []
20.831884    | SETUP      | 8.0      | 8     | 02 01 00 00 83 00 00 00
20.831909    | IN         | 8.0      | 0     | []
20.837303    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
20.837328    | IN         | 8.0      | 1     | 32
20.837333    | OUT        | 8.0      | 0     | []
20.837487    | SETUP      | 8.0      | 8     | a2 81 00 01 00 00 03 00
20.837617    | IN         | 8.0      | 3     | 44 ac 00
20.837622    | OUT        | 8.0      | 0     | []
20.888192    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
20.888223    | OUT        | 8.0      | 3     | 80 bb 00
20.888248    | IN         | 8.0      | 0     | []
20.899423    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
20.899457    | OUT        | 8.0      | 3     | 80 bb 00
20.899482    | IN         | 8.0      | 0     | []
20.899667    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
20.899698    | OUT        | 8.0      | 3     | 80 bb 00
20.899723    | IN         | 8.0      | 0     | []
20.900108    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
20.900137    | OUT        | 8.0      | 3     | 80 bb 00
20.900159    | IN         | 8.0      | 0     | []
20.900318    | SETUP      | 8.0      | 8     | 22 01 00 01 05 00 03 00
20.900350    | OUT        | 8.0      | 3     | 80 bb 00
20.900375    | IN         | 8.0      | 0     | []
20.900514    | SETUP      | 8.0      | 8     | 22 01 00 01 86 00 03 00
20.900545    | OUT        | 8.0      | 3     | 80 bb 00
20.900570    | IN         | 8.0      | 0     | []
20.900748    | SETUP      | 8.0      | 8     | a2 81 00 01 86 00 03 00
20.900856    | IN         | 8.0      | 3     | 80 bb 00
20.900862    | OUT        | 8.0      | 0     | []
20.951755    | SETUP      | 8.0      | 8     | c0 49 00 00 00 00 01 00
20.951780    | IN         | 8.0      | 1     | 32
20.951785    | OUT        | 8.0      | 0     | []
20.951964    | SETUP      | 8.0      | 8     | 40 49 32 00 00 00 00 00
20.952183    | IN         | 8.0      | 0     | []
20.952392    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
20.952403    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
20.956405    | IN         | 8.6      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
20.956443    | OUT        | 8.5      | 512   | 00 00 00 00 00 00 00 00 00 00 00 00 00 .....
....
....
....

```


Based on the provided USB control transfers and endpoint streaming timestamps, we can dissect the exact sequence the macOS driver uses to transition sample rates cleanly without requiring a heavy-handed USB bus reset.

The trace reveals 5 distinct sample rate transitions occurring at roughly **10.82s**, **12.56s**, **16.38s**, **17.76s**, and **20.82s**. Let’s analyze the values being targeted, look closely at the handshake pattern, and map out an elegant state machine for ALSA.

---

## 1. Data Interpretation (Payload De-serialization)

The sample rates in the payload are transmitted as 3-byte integers in **Little-Endian** format. We can decode them as follows:

* `44 ac 00` $\rightarrow$ `0x00AC44` = **44,100 Hz (44.1 kHz)**
* `80 bb 00` $\rightarrow$ `0x00BB80` = **48,000 Hz (48 kHz)**
* `88 58 01` $\rightarrow$ `0x015888` = **88,200 Hz (88.2 kHz)**
* `00 77 01` $\rightarrow$ `0x017700` = **96,000 Hz (96 kHz)**

### The Transition Timeline

1. **@ 10.822s:** Transitions from 44.1 kHz $\rightarrow$ **48 kHz**
2. **@ 12.559s:** Transitions from 48 kHz $\rightarrow$ **44.1 kHz**
3. **@ 16.379s:** Transitions from 44.1 kHz $\rightarrow$ **88.2 kHz**
4. **@ 17.765s:** Transitions from 88.2 kHz $\rightarrow$ **96 kHz**
5. **@ 20.827s:** Transitions from 96 kHz $\rightarrow$ **48 kHz**

---

## 2. The Exact Anatomy of the Handshake

Every single sample rate change block follows a completely identical, highly systematic sequence of exactly **4 phases**.

### Phase A: Teardown & Endpoint Halting

The driver immediately tears down the operational state by flipping interface alternate settings and hitting the endpoint pipes with standard USB requests:

* **Set Interface 0, Alt Setting 1:** `01 0b 00 00 01 00 00 00` (`bRequest=SET_INTERFACE`, `wValue=1`, `wIndex=0`)
* **Set Interface 0, Alt Setting 0:** `01 0b 00 00 00 00 00 00` (`wValue=0`, `wIndex=0`) — *This effectively silences/deactivates the audio interface.*
* **Set Interface 1, Alt Setting 0:** `01 0b 00 00 01 00 00 00` then `01 0b 01 00 00 00 00 00`
* **Clear Feature (ENDPOINT_HALT):** The driver clears stalls or resets toggles explicitly on the endpoints:
* Endpoint `0x86` (Capture): `02 01 00 00 86 00 00 00`
* Endpoint `0x05` (Playback): `02 01 00 00 05 00 00 00`
* Endpoint `0x83` (Feedback/Sync): `02 01 00 00 83 00 00 00`



### Phase B: Query Current Status

Before applying the new rate, the driver executes vendor or class-specific reads:

* **Vendor Read:** `c0 49 00 00 00 00 01 00` $\rightarrow$ Device returns `32` (Hex) / `0x32`.
* **Get Sample Rate:** `a2 81 00 01 00 00 03 00` (`bmRequestType=0xA2` [Class, Interface, Recipient], `bRequest=0x81` [GET_CUR], `wValue=0x0100` [SAMPLING_FREQ_CONTROL]). It reads the *old* rate first to confirm the state.

### Phase C: The "Shotgun" Rate Selection

This is likely why your driver is currently failing without a bus reset. **The device expects a hammering sequence of SET commands paired with alternating endpoint indices, concluded by a GET validation read.**
Looking at the 44.1 kHz $\rightarrow$ 48 kHz block:

1. `SET_CUR` to Endpoint `0x86`: `22 01 00 01 86 00 03 00` $\rightarrow$ Payload: `80 bb 00` (48k)
2. *~10ms pause*
3. `SET_CUR` to Endpoint `0x86`: `22 01 00 01 86 00 03 00` $\rightarrow$ Payload: `80 bb 00` (48k)
4. `SET_CUR` to Endpoint `0x05`: `22 01 00 01 05 00 03 00` $\rightarrow$ Payload: `80 bb 00` (48k)
5. `SET_CUR` to Endpoint `0x86`: `22 01 00 01 86 00 03 00` $\rightarrow$ Payload: `80 bb 00` (48k)
6. `SET_CUR` to Endpoint `0x05`: `22 01 00 01 05 00 03 00` $\rightarrow$ Payload: `80 bb 00` (48k)
7. `SET_CUR` to Endpoint `0x86`: `22 01 00 01 86 00 03 00` $\rightarrow$ Payload: `80 bb 00` (48k)
8. **Validation GET_CUR:** `a2 81 00 01 86 00 03 00` $\rightarrow$ Device echoes back `80 bb 00` to acknowledge the internal PLL lock.

### Phase D: Vendor Wake-up & Stream Resume

Once validated, the driver forces an explicit vendor write command to kick the state machine before audio buffers hit the wire:

* **Vendor Read:** `c0 49 00 00 00 00 01 00` $\rightarrow$ Returns `32`.
* **Vendor Write (The Ignition):** `40 49 32 00 00 00 00 00` (`bmRequestType=0x40`, `bRequest=0x49`, `wValue=0x0032`).
* Immediately following this write (~1-2ms later), the 512-byte zero-padded audio streaming frames cleanly resume on endpoints `8.5` and `8.6`.

---

## 3. Recommended ALSA Driver Implementation

To replace your hard `usb_reset_device()` loop, map the sequence into your ALSA driver's clock or PCM operations (such as your `hw_params` or a custom rate-switch function).

```c
// Pseudo-code implementation for your custom ALSA kernel driver

static int reloop_jockey3_change_rate(struct snd_usb_audio *chip, int rate)
{
    u8 data[3];
    u8 status_val;
    struct usb_device *dev = chip->dev;

    // Convert rate to 3-byte little endian
    data[0] = rate & 0xff;
    data[1] = (rate >> 8) & 0xff;
    data[2] = (rate >> 16) & 0xff;

    // PHASE A: Teardown Interfaces & Clear Halts
    usb_set_interface(dev, 0, 1);
    usb_set_interface(dev, 0, 0);
    usb_set_interface(dev, 1, 0);
    usb_set_interface(dev, 1, 1); // Note: adapt indices if asymmetric
    
    usb_clear_halt(dev, usb_rcvisocpipe(dev, 0x86));
    usb_clear_halt(dev, usb_sndisocpipe(dev, 0x05));
    usb_clear_halt(dev, usb_rcvisocpipe(dev, 0x83));

    // PHASE B: Pre-queries
    usb_control_msg(dev, usb_rcvctrlpipe(dev, 0), 0x49, 0xC0, 0, 0, &status_val, 1, 1000);
    // (Optional) GET_CUR old rate read goes here if your device requires it to flush buffer

    // PHASE C: The Multi-Endpoint Shotgun Sequence 
    // Target Endpoint 0x86
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x01, 0x22, 0x0100, 0x0086, data, 3, 1000);
    msleep(10); // Crucial ~10ms timing delay observed in trace
    
    // Alternating commands
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x01, 0x22, 0x0100, 0x0086, data, 3, 1000);
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x01, 0x22, 0x0100, 0x0005, data, 3, 1000);
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x01, 0x22, 0x0100, 0x0086, data, 3, 1000);
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x01, 0x22, 0x0100, 0x0005, data, 3, 1000);
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x01, 0x22, 0x0100, 0x0086, data, 3, 1000);

    // Validate Lock
    usb_control_msg(dev, usb_rcvctrlpipe(dev, 0), 0x81, 0xA2, 0x0100, 0x0086, data, 3, 1000);

    // PHASE D: Vendor Ignition Register
    usb_control_msg(dev, usb_rcvctrlpipe(dev, 0), 0x49, 0xC0, 0, 0, &status_val, 1, 1000);
    usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0x49, 0x40, 0x0032, 0, NULL, 0, 1000);

    return 0;
}

```

### Key Takeaway for Your Driver

The reason your driver has been flaky without a full reset is almost certainly due to the missing explicit **`Clear Feature: ENDPOINT_HALT`** calls across *all three* associated streaming endpoints simultaneously, coupled with the missing vendor register strobe (`0x40, 0x49, wValue=0x0032`) right before resumption. If you implement this precise sequence, the hardware clock state machine should settle beautifully.


for Phase A, the endpoint halting.  The current driver re-submits the URB from within the callback handler, resulting in a continuous flow.  So it will be important to properly coordinate/sychronize the stopping of the URBs (ie. not resubmitting) versus the  teardown packets

The "Hammering" aspect of the the rate selection in phase C worries me a bit; it feels hard to believe that the proprietary driver just sends a fixed/hardcoded(?) sequence of similar SET_CUR commands without feedback.  Almost feels like a hack to cope with some obscure flaws in the firmware, as one would expect a reliable handshake instead of hammering....

Is this hammering consistent with all the rate changes captured?


Yes, your intuition is spot on. "Hammering" control transfers like that is usually a classic sign of a driver developer working around a finicky, race-condition-prone USB microcontroller firmware—likely an off-the-shelf chip or custom FPGA core that needs time to switch its internal PLL clock multiplier and doesn't implement proper clock-ready polling or USB NAKing during the transition.

To answer your question directly: **Yes, the hammering pattern is completely consistent across all 5 rate changes captured in your trace.** Every single transition—regardless of the target rate—uses the exact same cadence of commands, target endpoints, and relative timing. Let's look at the exact evidence from your log to see how uniform it actually is.

---

## The Cross-Rate Evidence

If we extract just the **Phase C Sequence** from each transition block, you can see that the sequence length, the target endpoints (`0x86` and `0x05`), and the interleaved order do not change:

### 1. 44.1 kHz $\rightarrow$ 48 kHz (at 10.883s)

* `SET_CUR` -> `0x86` (`80 bb 00`)
* *~10ms delay*
* `SET_CUR` -> `0x86` (`80 bb 00`)
* `SET_CUR` -> `0x05` (`80 bb 00`)
* `SET_CUR` -> `0x86` (`80 bb 00`)
* `SET_CUR` -> `0x05` (`80 bb 00`)
* `SET_CUR` -> `0x86` (`80 bb 00`)
* `GET_CUR` <- `0x86` (Returns `80 bb 00`)

### 2. 48 kHz $\rightarrow$ 44.1 kHz (at 12.620s)

* `SET_CUR` -> `0x86` (`44 ac 00`)
* *~10ms delay*
* `SET_CUR` -> `0x86` (`44 ac 00`)
* `SET_CUR` -> `0x05` (`44 ac 00`)
* `SET_CUR` -> `0x86` (`44 ac 00`)
* `SET_CUR` -> `0x05` (`44 ac 00`)
* `SET_CUR` -> `0x86` (`44 ac 00`)
* `GET_CUR` <- `0x86` (Returns `44 ac 00`)

### 3. 44.1 kHz $\rightarrow$ 88.2 kHz (at 16.440s)

* Same exact order targeting `0x86`, delay, `0x86`, `0x05`, `0x86`, `0x05`, `0x86`, followed by a `GET_CUR` validation verification loop, using payload `88 58 01`.

### 4. 88.2 kHz $\rightarrow$ 96 kHz (at 17.825s)

* Same exact structure using payload `00 77 01`.

### 5. 96 kHz $\rightarrow$ 48 kHz (at 19.372s)

* Same exact structure using payload `44 ac 00`.

---

## Why Is the Proprietary Driver Doing This?

Because it's hardcoded and completely independent of the target frequency, this sequence is baked directly into the proprietary driver's rate-change function. There are two highly probable engineering reasons for this "hack":

1. **Microcontroller Buffer/FIFO Clearing:** When changing sample rates, the device's internal buffer pointers for the capture (`0x86`) and playback (`0x05`) channels likely get desynchronized or stuck in an invalid state. Sending a control transfer to an endpoint on certain chipsets forces an internal hardware state-machine reset for that specific endpoint's internal FIFO ring buffer.
2. **PLL Settling Window (The 10ms Delay):** Notice that after the very first `SET_CUR`, there is a significant ~10ms gap before the rest of the burst. The driver is giving the hardware a moment to switch the clock dividers. The subsequent burst of repeated commands acts as a brute-force method to ensure the configuration register actually latches while the hardware clock lines are unstable or noisy.

---

## Managing Your URB Lifecycle in ALSA

Your concern about Phase A coordination is critical. Since your driver currently resubmits URBs from within their completion callbacks, simply firing off `usb_set_interface` or control packets out-of-band *will* cause race conditions, kernel panics, or endpoint stalls.

To safely implement this without a hard reset, you need to transition your streaming endpoints through an explicit **Quiesce Phase** before executing the control sequence.

### Safe Coordination Strategy

1. **Set a State Flag:** Set a driver-specific state flag (e.g., `chip->quiescing = 1`) under a spinlock or mutex.
2. **Short-Circuit the Callbacks:** In your URB completion handler, read this flag. If it's true, **do not resubmit the URB**. Simply return early.
3. **Kill the Active Pipelines:** Call `usb_kill_urb()` on all your in-flight audio URBs from your main thread context. This safely forces any active URBs out of the host controller schedule and guarantees they are dead.
4. **Execute Handshake:** Run Phase A (`usb_set_interface`, `usb_clear_halt`), Phase B, Phase C (the hammering sequence), and Phase D.
5. **Clear Flag & Allocate:** Reset the state flag, re-allocate/initialize your URB buffers for the new rate, and resubmit the initial batch to kickstart the continuous callback loop.

Would you like to look at how to hook this cleanly into ALSA's `hw_params` or `prepare` PCM operators to ensure the kernel ALSA subsystem coordinates safely with your state flag?




