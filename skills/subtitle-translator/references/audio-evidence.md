# Audio Evidence

Read when unclear automatic captions need speech recognition or when available audio can support timing adjustments. The main agent coordinates this work and supplies the resulting observations to the translation workers that need them.

## Resolve the Available Capability

Start with the session's exposed tools, the calling project's environment, and any provided runtime information. Identify a local speech runtime with an executable interface and existing model data, then consult its own usage and device support. Confirm that it can read the supplied media or an extract produced by an available media tool.

Use supported GPU execution when the selected runtime and model can operate on that device. Use CPU when GPU execution is unavailable or fails for an identified backend or resource reason. Retain useful completed results when changing the execution device, and record the actual runtime, model, device, and any fallback used.

If no usable local recognition path or matching audio is available, continue the supported translation work from the available evidence and record the unresolved evidence limitation. Keep material decisions in `pending` until an interpretation has been accepted from the available context.

## Obtain Targeted Recognition

Collect unclear original-time intervals from translation work together with the source cue IDs, competing readings, and the context needed to interpret them. Combine overlapping requests and retain enough surrounding speech to recognize complete phrases. Reuse the loaded runtime where its interface supports it, coordinating requests to avoid competing model loads.

Use the selected tool's own interval support or extract the required audio with an available media tool. Preserve the extraction offset. A time returned relative to a clip becomes an original-media time by adding that clip's start offset; inspect the runtime's timestamp convention before making this conversion.

Retain the original automatic caption and the new recognition result as separate observations. Provide the relevant outputs and any documented confidence or timing information to the responsible translation worker. Judge disagreements through the surrounding dialogue, speaker intent, terminology, and available audio. Revisit earlier terminology decisions when stronger evidence changes an interpretation.

Record accepted corrections and important remaining uncertainty in the work notes. Reuse those observations when repairing the same passage. Further recognition should address an identified question or execution failure.

## Establish Timing

Choose timing evidence according to what the available capability supplies:

- Word timestamps or speech alignment relate text to the media timeline; inspect the text correspondence and surrounding speech when recognition is uncertain.
- Voice activity and waveforms locate speech or pauses; identify which utterance belongs to a proposed cue before using those boundaries.
- Direct review of the matching media can assess onset, cutoff, turn changes, and the viewing rhythm of the composed subtitles.

Coordinate natural segmentation with the timing evidence and the time needed to read the translation. Recheck passage joins when split or merged sentences move their boundaries. Keep deliberate simultaneous speech distinct from accidental overlap, and use available scene context when a timing change could reveal information too early.

Report whether timing was derived from source cues, recognition timestamps, alignment, or reviewed audio/video. Distinguish structural timing checks from confirmed speech synchronization, and identify the portions actually reviewed.
