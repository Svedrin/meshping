# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on; hl python;
#
# Python binding for octo's oping library.

from libc.stdint cimport uint8_t, uint16_t, uint32_t

cdef extern from "oping.h":
    ctypedef struct pinghost:
        pass

    ctypedef struct pingobj:
        pass

    ctypedef pinghost pinghost_t
    ctypedef pinghost pingobj_iter_t
    ctypedef pingobj  pingobj_t

    pingobj_t *ping_construct ()
    void ping_destroy (pingobj_t *obj)

    int ping_setopt (pingobj_t *obj, int option, void *value)

    int ping_send (pingobj_t *obj)

    int ping_host_add (pingobj_t *obj, const char *host)
    int ping_host_remove (pingobj_t *obj, const char *host)

    pingobj_iter_t *ping_iterator_get (pingobj_t *obj)
    pingobj_iter_t *ping_iterator_next (pingobj_iter_t *iter)

    int ping_iterator_get_info (pingobj_iter_t *iter, int info,
                                void *buffer, size_t *buffer_len)

    const char *ping_get_error (pingobj_t *obj)

    void *ping_iterator_get_context (pingobj_iter_t *iter)
    void  ping_iterator_set_context (pingobj_iter_t *iter, void *context)


cdef PING_OPT_TIMEOUT = 0x01
cdef PING_OPT_TTL     = 0x02
cdef PING_OPT_AF      = 0x04
cdef PING_OPT_DATA    = 0x08
cdef PING_OPT_SOURCE  = 0x10
cdef PING_OPT_DEVICE  = 0x20
cdef PING_OPT_QOS     = 0x40

cdef PING_DEF_TIMEOUT = 1.0
cdef PING_DEF_TTL     = 255

cdef PING_INFO_HOSTNAME =  1
cdef PING_INFO_ADDRESS  =  2
cdef PING_INFO_FAMILY   =  3
cdef PING_INFO_LATENCY  =  4
cdef PING_INFO_SEQUENCE =  5
cdef PING_INFO_IDENT    =  6
cdef PING_INFO_DATA     =  7
cdef PING_INFO_USERNAME =  8
cdef PING_INFO_DROPPED  =  9
cdef PING_INFO_RECV_TTL = 10
cdef PING_INFO_RECV_QOS = 11


class PingError(RuntimeError):
    pass


cdef class PingObj:
    cdef pingobj_t* _c_pingobj

    default_timeout = PING_DEF_TIMEOUT
    default_ttl     = PING_DEF_TTL

    def __cinit__(self):
        self._c_pingobj = ping_construct()
        if self._c_pingobj is NULL:
            raise MemoryError()

    def __dealloc__(self):
        if self._c_pingobj is not NULL:
            ping_destroy(self._c_pingobj)

    def send(self):
        ret = ping_send(self._c_pingobj)
        if ret < 0:
            raise PingError(ping_get_error(self._c_pingobj))
        return ret

    def add_host(self, char *host):
        if len(host) > 50:
            raise ValueError("name is too long (max 50 chars)")
        if ping_host_add(self._c_pingobj, host) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def remove_host(self, char *host):
        if ping_host_remove(self._c_pingobj, host) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def get_hosts(self):
        cdef pingobj_iter_t *iter

        cdef char     hostname[51]
        cdef char     hostaddr[40]
        cdef double   latency
        cdef uint32_t dropped
        cdef uint32_t seqnr
        cdef uint16_t ident
        cdef int      recvttl
        cdef uint8_t  recvqos

        cdef size_t buflen

        hosts = []

        iter = ping_iterator_get(self._c_pingobj)
        while iter != NULL:
            buflen = sizeof(hostname) - 1
            ping_iterator_get_info(iter, PING_INFO_USERNAME, &hostname, &buflen)
            hostname[buflen] = 0

            buflen = sizeof(hostaddr) - 1
            ping_iterator_get_info(iter, PING_INFO_ADDRESS,  &hostaddr, &buflen)
            hostaddr[buflen] = 0

            buflen = sizeof(latency)
            ping_iterator_get_info(iter, PING_INFO_LATENCY,  &latency,  &buflen)

            buflen = sizeof(dropped)
            ping_iterator_get_info(iter, PING_INFO_DROPPED,  &dropped,  &buflen)

            buflen = sizeof(seqnr)
            ping_iterator_get_info(iter, PING_INFO_SEQUENCE, &seqnr,    &buflen)

            buflen = sizeof(ident)
            ping_iterator_get_info(iter, PING_INFO_IDENT,    &ident,    &buflen)

            buflen = sizeof(recvttl)
            ping_iterator_get_info(iter, PING_INFO_RECV_TTL, &recvttl,  &buflen)

            buflen = sizeof(recvqos)
            ping_iterator_get_info(iter, PING_INFO_RECV_QOS, &recvqos,  &buflen)

            hosts.append({
                "name":    hostname,
                "addr":    hostaddr,
                "latency": latency,
                "dropped": dropped,
                "seqnr":   seqnr,
                "ident":   ident,
                "recvttl": recvttl,
                "recvqos": recvqos,
            })

            iter = ping_iterator_next(iter)

        return hosts

    def set_timeout(self, double val):
        if ping_setopt(self._c_pingobj, PING_OPT_TIMEOUT, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def set_ttl(self, int val):
        if ping_setopt(self._c_pingobj, PING_OPT_TTL, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def set_af(self, int val):
        if ping_setopt(self._c_pingobj, PING_OPT_AF, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def set_data(self, char *val):
        if ping_setopt(self._c_pingobj, PING_OPT_DATA, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def set_source(self, char *val):
        if ping_setopt(self._c_pingobj, PING_OPT_SOURCE, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def set_device(self, char *val):
        if ping_setopt(self._c_pingobj, PING_OPT_DEVICE, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))

    def set_qos(self, uint8_t val):
        if ping_setopt(self._c_pingobj, PING_OPT_QOS, &val) < 0:
            raise PingError(ping_get_error(self._c_pingobj))
