import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.FileInputStream;
import java.util.Arrays;

/** Small authored ART/JCA acceptance, never an application/provider capability. */
public final class PublisherCryptoBatchProbe {
    public static void main(String[] args) throws Exception {
        try (DataInputStream input = new DataInputStream(new FileInputStream(args[0]))) {
            if (input.readInt() != 0x50424a31) throw new IllegalArgumentException();
            int count = input.readInt();
            if (count < 1 || count > 128) throw new IllegalArgumentException();
            for (int index=0;index<count;index++) {
                int length = input.readInt();
                if (length < 1 || length > 65536) throw new IllegalArgumentException();
                byte[] raw = new byte[length];input.readFully(raw);
                int expectedSize = input.readInt();
                if (expectedSize < -2 || expectedSize > 65536) throw new IllegalArgumentException();
                byte[] expected = expectedSize < 0 ? null : new byte[expectedSize];
                if (expected != null) input.readFully(expected);
                byte[] actual = null;boolean rejected = false;
                try { actual = PublisherCryptoProbe.execute(new DataInputStream(new ByteArrayInputStream(raw))); }
                catch (Exception invalid) { rejected = true; }
                if (expectedSize == -2 ? !rejected : rejected || !Arrays.equals(actual,expected))
                    throw new IllegalStateException("Authored JCA case failed: " + index);
            }
            if (input.read() != -1) throw new IllegalArgumentException();
            System.out.println("{\"schema\":\"toolkit-publisher-jca-probe-v1\",\"cases\":"+count+
                ",\"passed\":true,\"original_game_execution\":false,\"account_keys_reused\":false}");
        }
    }
}
