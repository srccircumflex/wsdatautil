#define PY_SSIZE_T_CLEAN
#include <Python.h>

#if __ARM_NEON
#include <arm_neon.h>
#elif __SSE2__
#include <emmintrin.h>
#endif


static char * _masking(char *input, Py_ssize_t len, char *mask) {
    Py_ssize_t i = 0;

    char *output = (char*)malloc(len * sizeof(char));
    if (output == NULL) {
        PyErr_Format(
            PyExc_SystemError,
            "Memory allocation failed"
        );
        return NULL;
    };
    char *p_output = output;
    
    {
#if __ARM_NEON
        Py_ssize_t input_len_128 = len & ~15;
        uint8x16_t mask_128 = vreinterpretq_u8_u32(vdupq_n_u32(*(uint32_t *)mask));
        for (; i < input_len_128; i += 16) {
            uint8x16_t in_128 = vld1q_u8((uint8_t *)(input + i));
            uint8x16_t out_128 = veorq_u8(in_128, mask_128);
            vst1q_u8((uint8_t *)(output + i), out_128);
        }
#elif __SSE2__
        Py_ssize_t input_len_128 = len & ~15;
        __m128i mask_128 = _mm_set1_epi32(*(uint32_t *)mask);

        for (; i < input_len_128; i += 16) {
            __m128i in_128 = _mm_loadu_si128((__m128i *)(input + i));
            __m128i out_128 = _mm_xor_si128(in_128, mask_128);
            _mm_storeu_si128((__m128i *)(output + i), out_128);
        }
#else
        Py_ssize_t input_len_64 = len & ~7;
        uint32_t mask_32 = *(uint32_t *)mask;
        uint64_t mask_64 = ((uint64_t)mask_32 << 32) | (uint64_t)mask_32;

        for (; i < input_len_64; i += 8) {
            *(uint64_t *)(output + i) = *(uint64_t *)(input + i) ^ mask_64;
        }
#endif
    }
    
    for (; i < len; i++) {
        output[i] = input[i] ^ mask[i & 3];
    }
    return p_output;
}


static PyObject * masking(PyObject *self, PyObject *args) {
    PyObject  *i_payload;
    PyObject  *i_mask;

    if (!PyArg_ParseTuple(args, "OO", &i_payload, &i_mask)) {
        return NULL;
    }

    char       *mask;
    Py_ssize_t  mask_len;
    
    if (PyBytes_AsStringAndSize(i_mask, &mask, &mask_len) == -1) {
        return NULL;
    }
    
    if (mask_len != 4) {
        PyErr_Format(
            PyExc_ValueError,
            "invalid mask: length != 4"
        );
        return NULL;
    }

    char       *payload;
    Py_ssize_t  payload_len;

    if (PyBytes_AsStringAndSize(i_payload, &payload, &payload_len) == -1) {
        return NULL;
    }

    char *o_obj_data = _masking(payload, payload_len, mask);
    if (o_obj_data == NULL) {
        return NULL;
    }
    PyObject *o_obj = PyBytes_FromStringAndSize(o_obj_data, payload_len);
    free(o_obj_data);
    return o_obj;
}


static PyObject * build(PyObject *self, PyObject *args) {
    uint8_t  i_fin;
    uint8_t  i_rsv1;
    uint8_t  i_rsv2;
    uint8_t  i_rsv3;
    uint8_t  i_opcode;
    PyObject *i_mask = NULL;
    PyObject *i_payload = NULL;

    if (!PyArg_ParseTuple(args, "ppppiOO", &i_fin, &i_rsv1, &i_rsv2, &i_rsv3, &i_opcode, &i_mask, &i_payload)) {
        return NULL;
    }
    
    char       *mask;
    Py_ssize_t  mask_len;

    if (PyBytes_AsStringAndSize(i_mask, &mask, &mask_len) == -1) {
        return NULL;
    }

    uint8_t masked;
    if (mask_len == 4) {
        masked = 0b10000000;
    } else if (mask_len == 0) {
        masked = 0b00000000;
    } else {
        PyErr_Format(
            PyExc_ValueError,
            "invalid mask: length != 4"
        );
        return NULL;
    }

    char       *payload;
    Py_ssize_t  amount;
    
    if (PyBytes_AsStringAndSize(i_payload, &payload, &amount) == -1) {
        return NULL;
    }
    
    int header_offset = 2;
    
    uint8_t amount_spec;
    int _amount_spec_len;
    if (amount <= 125) {
        amount_spec = amount;
        _amount_spec_len = 0;
    } else if (amount <= 65535) {
        amount_spec = 0b01111110;
        _amount_spec_len = 2;
    } else {
        amount_spec = 0b01111111;
        _amount_spec_len = 8;
    }
    
    int total_amount = header_offset + _amount_spec_len + mask_len + amount;
    PyObject *o_obj = PyBytes_FromStringAndSize(NULL, total_amount);
    if (o_obj == NULL) {
        PyErr_Format(
            PyExc_SystemError,
            "could not create PyBytes"
        );
        return NULL;
    };
    char *o_obj_data = PyBytes_AS_STRING(o_obj);
    
    if (i_fin) {
        i_fin = 0b10000000;
    }
    if (i_rsv1) {
        i_rsv1 = 0b01000000;
    }
    if (i_rsv2) {
        i_rsv2 = 0b00100000;
    }
    if (i_rsv3) {
        i_rsv3 = 0b00010000;
    }

    o_obj_data[0] = i_fin|i_rsv1|i_rsv2|i_rsv3|i_opcode;
    o_obj_data[1] = masked | amount_spec;
    
    if (_amount_spec_len == 2) {
        o_obj_data[2] = (amount >> 8)  & 0b11111111;
        o_obj_data[3] =  amount        & 0b11111111;
    } else if (_amount_spec_len == 8) {
        o_obj_data[2] = (amount >> 56) & 0b11111111;
        o_obj_data[3] = (amount >> 48) & 0b11111111;
        o_obj_data[4] = (amount >> 40) & 0b11111111;
        o_obj_data[5] = (amount >> 32) & 0b11111111;
        o_obj_data[6] = (amount >> 24) & 0b11111111;
        o_obj_data[7] = (amount >> 16) & 0b11111111;
        o_obj_data[8] = (amount >> 8)  & 0b11111111;
        o_obj_data[9] =  amount        & 0b11111111;
    }

    header_offset += _amount_spec_len;
    
    if (masked) {
        memcpy(o_obj_data + header_offset, mask, 4);
        header_offset += 4;
        char *masked_payload = _masking(payload, amount, mask);
        if (masked_payload == NULL) {
            PyObject_Del(o_obj);
            return NULL;
        }
        memcpy(o_obj_data + header_offset, masked_payload, amount);
        free(masked_payload);
    } else {
        memcpy(o_obj_data + header_offset, payload, amount);
    }

    return o_obj;
}

static PyObject * parse(PyObject *self, PyObject *args) {
    PyObject   *i_obj;
    Py_ssize_t  i_len;
    char       *i_data;
    int         i_autodemask;

    char     *o_mask = NULL;
    char     *o_masked_payload = NULL;
    PyObject *o_obj = NULL;
    
    if (!PyArg_ParseTuple(args, "Op", &i_obj, &i_autodemask))
    {
        goto exit;
    }

    if (PyBytes_AsStringAndSize(i_obj, &i_data, &i_len) == -1) {
        goto exit;
    }

    unsigned char *_input = (unsigned char *)i_data;

    char _b1 = _input[0];
    int      fin         = (_b1 & 0b10000000) >> 7;
    int      rsv1        = (_b1 & 0b01000000) >> 6;
    int      rsv2        = (_b1 & 0b00100000) >> 5;
    int      rsv3        = (_b1 & 0b00010000) >> 4;
    int      opcode      = (_b1 & 0b00001111);
    char _b2 = _input[1];
    int      masked      = (_b2 & 0b10000000) >> 7;
    int      amount_spec = (_b2 & 0b01111111);
    uint64_t amount;

    uint64_t _header_offset = 2;
    
    if ((uint64_t)i_len < _header_offset) {
        PyErr_Format(
            PyExc_ValueError,
            "invalid frame: data length < 2"
        );
        goto exit;
    }
    
    if (amount_spec == 126) {
        amount =  (uint64_t)_input[2];
        amount <<= 8;
        amount |= (uint64_t)_input[3];
        _header_offset += 2;
    } else if (amount_spec == 127) {
        amount =  (uint64_t)_input[2];
        amount <<= 8;
        amount |= (uint64_t)_input[3];
        amount <<= 8;
        amount |= (uint64_t)_input[4];
        amount <<= 8;
        amount |= (uint64_t)_input[5];
        amount <<= 8;
        amount |= (uint64_t)_input[6];
        amount <<= 8;
        amount |= (uint64_t)_input[7];
        amount <<= 8;
        amount |= (uint64_t)_input[8];
        amount <<= 8;
        amount |= (uint64_t)_input[9];
        _header_offset += 8;
    } else {
        amount = amount_spec;
    }
    
    o_mask = (char*)malloc(4 * sizeof(char));
    if (o_mask == NULL) {
        PyErr_Format(
            PyExc_SystemError,
            "Memory allocation failed"
        );
        goto exit;
    };
    if (masked) {
        memcpy(o_mask, _input + _header_offset, 4);
        _header_offset += 4;
    }

    uint64_t _edl = _header_offset + amount;
    if (_edl != (uint64_t)i_len) {
        PyErr_Format(
            PyExc_ValueError,
            "invalid frame: data length (%d) != expected data length (%d)",
            i_len, _edl
        );
        goto exit;
    }

    if (i_autodemask & masked) {
        o_masked_payload = _masking((char*)_input + _header_offset, amount, o_mask);
        if (o_masked_payload == NULL) {
            goto exit;
        }
        o_obj = Py_BuildValue(
            "(i,i,i,i,i,i,i,i,y#,y#)",
            fin, rsv1, rsv2, rsv3, opcode, masked, amount_spec, amount, o_mask, 4, o_masked_payload, amount
        );
    } else {
        o_obj = Py_BuildValue(
            "(i,i,i,i,i,i,i,i,y#,y#)",
            fin, rsv1, rsv2, rsv3, opcode, masked, amount_spec, amount, o_mask, 4, (char*)_input + _header_offset, amount
        );
    }

exit:
    free(o_mask);
    free(o_masked_payload);
    return o_obj;
}



static PyMethodDef wsframecoder_meth[] = {
    {
        "parse",
        (PyCFunction)parse,
        METH_VARARGS,
        "parse [and decode] a WebSocket frame <- (streamdata, auto_demask) -> (fin, rsv1, rsv2, rsv3, opcode, masked, amount_spec, amount, mask, payload)",
    },
    {
        "build",
        (PyCFunction)build,
        METH_VARARGS,
        "create a WebSocket frame <- (fin, rsv1, rsv2, rsv3, opcode, mask, payload) -> streamdata",
    },
    {
        "masking",
        (PyCFunction)masking,
        METH_VARARGS,
        "apply masking to a WebSocket payload <- (payload, mask) -> payload",
    },
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef wsframecoder_mod = {
    PyModuleDef_HEAD_INIT,
    "_wsframecoder",
    "c implemented coders for WebSocket frames",
    -1,
    wsframecoder_meth,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit__wsframecoder(void) {
    return PyModule_Create(&wsframecoder_mod);
}
