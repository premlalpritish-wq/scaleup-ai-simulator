"""Worker processes that talk to the existing scientific models.

Importing this package pulls in nothing; each worker module imports its own
model inside :func:`main` after ``sys.path`` has been pointed at that model's
package root.
"""