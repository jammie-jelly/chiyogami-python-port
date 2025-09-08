This is a Python port of [Chiyogami](https://github.com/rhee876527/chiyogami), a RESTful API pastebin written in Go that ships with an optional frontend.

#### Major Tool Replacements/Equivalents:

    Go - Python
    Gorilla Mux/Session - FastAPI
    encoding/json - ORJSONResponse
    GORM - SQLAlchemy

#### Deviations from original:

SQLAlchemy defaults to hard-delete mode therefore neither garbage collection of soft-deleted pastes nor DELETE_RETENTION are required with the port.

DeletedAt, a GORM default, is neither needed nor returned from responses. It is however maintained in the DB schema.

On paste creation, UserID defaults to null instead of 0 for unauthenticated users.

Healthcheck doesn't have cache like original.
