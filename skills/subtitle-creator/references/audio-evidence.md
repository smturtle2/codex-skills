# Audio Evidence

Read when timed speech evidence must be acquired from media, when a passage needs additional recognition, or when audio can support timing adjustments. The main agent coordinates acquisition and supplies the observations to the workers that need them.

## Resolve the Available Capability

Start with the session's exposed tools, the calling project's environment, and any provided runtime information. Identify a local speech runtime with an executable interface and existing model data, then consult its own usage and device support. Confirm that it can read the supplied media or an extract produced by an available media tool.

Use supported GPU execution when the selected runtime and model can operate on that device. Use CPU when GPU execution is unavailable or fails for an identified backend or resource reason. Retain useful completed results when changing the execution device, and record the actual runtime, model, device, and any fallback used.

Report any unavailable recognition capability with the affected media range. Continue work supported by existing evidence and retain unresolved acquisition ranges or material interpretation decisions until they have been addressed.

## Obtain Timed Speech Evidence

Establish the requested media range before recognition. When no subtitle track supplies the initial timed evidence, process that full range and retain the native result files, completed ranges, and any failures or pending ranges. Resume unprocessed portions using the retained results. A whole-file call can supply one completed range; divide work when the runtime or input requires it.

Normalize the actual recognized segments and their time anchors according to [work-data.md](work-data.md) before preparing common subtitle work. Distinguish a completed recognition call from a reliable reading of every utterance. Review empty output against the available speech evidence before accepting an empty subtitle track.

During composition, collect unclear original-time intervals together with source cue IDs, competing readings, and the context needed to interpret them. Combine overlapping requests and retain enough surrounding speech to recognize complete phrases. Reuse the loaded runtime where its interface supports it, coordinating requests to avoid competing model loads.

Use the selected tool's own interval support or extract the required audio with an available media tool. Preserve the extraction offset. A time returned relative to a clip becomes an original-media time by adding that clip's start offset; inspect the runtime's timestamp convention before making this conversion.

Retain initial subtitle or recognition evidence and subsequent recognition results as separate observations. Provide the relevant outputs and any documented confidence or timing information to the responsible worker. Judge disagreements through the surrounding dialogue, speaker intent, terminology, and available audio. Revisit earlier terminology decisions when stronger evidence changes an interpretation.

Record accepted corrections and important remaining uncertainty in the work notes. Reuse those observations when repairing the same passage. Further recognition should address an identified question or execution failure.

## Establish Timing

Choose timing evidence according to what the available capability supplies:

- Word timestamps or speech alignment relate text to the media timeline; inspect the text correspondence and surrounding speech when recognition is uncertain.
- Voice activity and waveforms locate speech or pauses; identify which utterance belongs to a proposed cue before using those boundaries.
- Direct review of the matching media can assess onset, cutoff, turn changes, and the viewing rhythm of the composed subtitles.

Coordinate natural segmentation with the timing evidence and the time needed to read the translation. Recheck passage joins when split or merged sentences move their boundaries. Keep deliberate simultaneous speech distinct from accidental overlap, and use available scene context when a timing change could reveal information too early.

Report whether timing was derived from source cues, recognition timestamps, alignment, or reviewed audio/video. Distinguish structural timing checks from confirmed speech synchronization, and identify the portions actually reviewed.
