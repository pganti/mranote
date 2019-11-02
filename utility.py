import cStringIO
import os.path

class Upload:
    '''Simple "sentinel" class that lets us identify file uploads in POST
    data mappings.
    '''
    def __init__(self, filename):
        self.filename = filename
    def __cmp__(self, other):
        return cmp(self.filename, other.filename)

boundary = '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254'
sep_boundary = '\n--' + boundary
end_boundary = sep_boundary + '--'

def mimeEncode(data, sep_boundary=sep_boundary, end_boundary=end_boundary):
    '''Take the mapping of data and construct the body of a
    multipart/form-data message with it using the indicated boundaries.
    '''
    ret = cStringIO.StringIO()
    for key, value in data.items():
        if not key:
            continue
        # handle multiple entries for the same name
        if type(value) != type([]): value = [value]
        for value in value:
            ret.write(sep_boundary)
            # if key starts with a '$' then the entry is a file upload
            if isinstance(value, Upload):
                ret.write('\nContent-Disposition: form-data; name="%s"'%key)
                ret.write('; filename="%s"\n\n'%value.filename)
                if value.filename:
                    value = open(os.path.join(value.filename), "rb").read()
                else:
                    value = ''
            else:
                ret.write('\nContent-Disposition: form-data; name="%s"'%key)
                ret.write("\n\n")
            ret.write(str(value))
            if value and value[-1] == '\r':
                ret.write('\n')  # write an extra newline
    ret.write(end_boundary)
    return ret.getvalue()
