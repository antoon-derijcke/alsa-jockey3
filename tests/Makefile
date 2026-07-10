# Makefile user-space testing code


# for compiling i386 target
#CC = i686-linux-gnu-gcc

CFLAGS += -Wall -O2


test: test_codec
	@echo running test
	./test_codec


clean:
	rm *.o test_codec ploytec_codec.[ch]


# create a symlink to the ploytec_codec.c to avoid it pulling-in the kernel headers when compiling the test code
ploytec_codec.c:
	ln -s ../ploytec_codec.c ploytec_codec.c
	ln -s ../ploytec_codec.h ploytec_codec.h

ploytec_codec.o: ploytec_codec.c
	$(CC) $(CFLAGS) -isystem stubs -c $< -o $@

ploytec_codec_new.o: ploytec_codec_new.c
	$(CC) $(CFLAGS) -isystem stubs -c $< -o $@


test_ploytec_codec.o: test_ploytec_codec.c
	$(CC) $(CFLAGS) -isystem stubs -c $< -o $@

test_codec: test_ploytec_codec.o ploytec_codec.o ploytec_codec_new.o
	$(CC) $(CFLAGS) -isystem stubs -o $@ $^

.PHONY: test_codec
