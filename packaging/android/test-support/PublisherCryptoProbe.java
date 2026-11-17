import io.github.firebird55.gameimmersiontoolkit.PublisherCryptoOperations;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.FileInputStream;

/** Authored-only host JCA reference protocol; never packaged into the app. */
public final class PublisherCryptoProbe {
    private static byte[] bytes(DataInputStream input) throws Exception {
        int size = input.readInt();if (size == -1) return null;
        if (size < 0 || size > PublisherCryptoOperations.MAX_BYTES) throw new IllegalArgumentException();
        byte[] result = new byte[size];input.readFully(result);return result;
    }
    static byte[] execute(DataInputStream input) throws Exception {
        byte[] result;String operation = input.readUTF();
        if (operation.equals("block")) {
            String algorithm = input.readUTF(), mode = input.readUTF();
            boolean decrypt = input.readBoolean();
            result = PublisherCryptoOperations.blockCipher(algorithm,mode,bytes(input),bytes(input),bytes(input),decrypt);
        } else if (operation.equals("verify")) {
            boolean value = PublisherCryptoOperations.rsaVerifySha256(bytes(input),bytes(input),bytes(input));
            result = new byte[]{(byte)(value ? 1 : 0)};
        } else if (operation.equals("decrypt")) {
            result = PublisherCryptoOperations.rsaDecryptPkcs1(bytes(input),bytes(input),bytes(input),bytes(input),bytes(input),bytes(input));
        } else throw new IllegalArgumentException();
        if (input.read() != -1) throw new IllegalArgumentException();
        return result;
    }
    public static void main(String[] args) throws Exception {
        try (DataInputStream input = new DataInputStream(new FileInputStream(args[0]));
             DataOutputStream output = new DataOutputStream(System.out)) {
            try {
                byte[] result = execute(input);
                output.writeInt(result == null ? -1 : result.length);
                if (result != null) output.write(result);
            } catch (Exception invalid) { output.writeInt(-2); }
        }
    }
}
