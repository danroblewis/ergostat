# support: the local half of the remote pair

A support desk whose tickets rise with the incidents another ergostat runs (`remotes: incidents`, read from
there and drawn as a remote subsystem). See `../README.md` for the pair and how to run it.

`incidents-calm` is a goal here on the remote's stock `incidents-open`: it is **watched here and acted on there**.
No block here may act on a remote part, so its loop is open on purpose.
