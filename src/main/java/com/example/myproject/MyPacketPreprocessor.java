package com.example.myproject;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.yamcs.TmPacket;
import org.yamcs.YConfiguration;
import org.yamcs.tctm.AbstractPacketPreprocessor;
import org.yamcs.utils.TimeEncoding;

/**
 * Component capable of modifying packet binary received from a link, before passing it further into Yamcs.
 * <p>
 * A single instance of this class is created, scoped to the link udp-in.
 * <p>
 * This is specified in the configuration file yamcs.myproject.yaml:
 * 
 * <pre>
 * ...
 * dataLinks:
 *   - name: udp-in
 *     class: org.yamcs.tctm.UdpTmDataLink
 *     stream: tm_realtime
 *     host: localhost
 *     port: 10015
 *     packetPreprocessorClassName: com.example.myproject.MyPacketPreprocessor
 * ...
 * </pre>
 * 
 * NOTE: CRC checking is disabled in this preprocessor since our test packets don't include CRC.
 */
public class MyPacketPreprocessor extends AbstractPacketPreprocessor {

    private Map<Integer, AtomicInteger> seqCounts = new HashMap<>();
    private Set<Integer> initializedApids = new HashSet<>();

    // APID 5 (Master HK) and APID 2000 (Events) may be bursty/variable; skip jump warnings for them.
    private static final int APID_MASTER_HK = 5;
    private static final int APID_EVENT = 2000;

    // Constructor used when this preprocessor is used without YAML configuration
    public MyPacketPreprocessor(String yamcsInstance) {
        this(yamcsInstance, YConfiguration.emptyConfig());
    }

    // Constructor used when this preprocessor is used with YAML configuration
    public MyPacketPreprocessor(String yamcsInstance, YConfiguration config) {
        super(yamcsInstance, config);
        // CRC checking is disabled - our packets don't have CRC appended
    }

    @Override
    public TmPacket process(TmPacket packet) {

        byte[] bytes = packet.getPacket();
        if (bytes.length < 6) { // Expect at least the length of CCSDS primary header
            eventProducer.sendWarning("SHORT_PACKET",
                    "Short packet received, length: " + bytes.length + "; minimum required length is 6 bytes.");

            // If we return null, the packet is dropped.
            return null;
        }

        // Verify continuity for a given APID based on the CCSDS sequence counter
        int apidseqcount = ByteBuffer.wrap(bytes).getInt(0);
        int apid = (apidseqcount >> 16) & 0x07FF;
        int seq = (apidseqcount) & 0x3FFF;

        if (apid == APID_EVENT && bytes.length > 6) {
            emitYamcsEventFromPacket(bytes);
        }

        AtomicInteger ai = seqCounts.computeIfAbsent(apid, k -> new AtomicInteger(seq));

        if (!initializedApids.contains(apid)) {
            // First packet for this APID establishes baseline sequence without warning.
            initializedApids.add(apid);
            ai.set(seq);
        } else {
            int oldseq = ai.getAndSet(seq);
            int delta = (seq - oldseq) & 0x3FFF;

            boolean ignoreApid = (apid == APID_MASTER_HK || apid == APID_EVENT);
            boolean isExpectedIncrement = (delta == 1);
            boolean isDuplicate = (delta == 0);

            if (!ignoreApid && !isExpectedIncrement && !isDuplicate) {
                eventProducer.sendWarning("SEQ_COUNT_JUMP",
                        "Sequence count jump for APID: " + apid + " old seq: " + oldseq + " newseq: " + seq);
            }
        }

        // Our custom packets don't include a secondary header with time information.
        // Use Yamcs-local time instead.
        packet.setGenerationTime(TimeEncoding.getWallclockTime());

        // Use the full 32-bits, so that both APID and the count are included.
        // Yamcs uses this attribute to uniquely identify the packet (together with the gentime)
        packet.setSequenceCount(apidseqcount);

        return packet;
    }

    private void emitYamcsEventFromPacket(byte[] packetBytes) {
        String msg = new String(packetBytes, 6, packetBytes.length - 6, StandardCharsets.UTF_8)
                .replace("\0", "")
                .trim();

        if (msg.isEmpty()) {
            return;
        }

        if (msg.startsWith("ERROR") || msg.startsWith("CRITICAL")) {
            eventProducer.sendError("FSW_EVENT", msg);
        } else if (msg.startsWith("WARN") || msg.startsWith("WARNING")) {
            eventProducer.sendWarning("FSW_EVENT", msg);
        } else {
            eventProducer.sendInfo("FSW_EVENT", msg);
        }
    }
}