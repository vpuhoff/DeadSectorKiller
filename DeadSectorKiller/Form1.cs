using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.Management;
using System.IO;

namespace DeadSectorKiller
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
        }

        private void button1_Click(object sender, EventArgs e)
        {
   
        }

        private void Form1_ResizeEnd(object sender, EventArgs e)
        {
            //plotBox1.CreateBox(10000);
            
        }

        private void timer1_Tick(object sender, EventArgs e)
        {
            
        }

        private void Form1_Load(object sender, EventArgs e)
        {
            InitDrives();
            GetDisks();
        }

        private long GetFileSize(string filename)
        {
            FileInfo f = new FileInfo(filename);
            long s1 = f.Length;
            return s1;
        }

        class DisksLite
        {
           public string Disk { get; set; }
        }
        private void GetDisks()
        {
            //try
            //{
            //    DriveInfo[] di = DriveInfo.GetDrives();
            //    BindingSource bs = new BindingSource();
            //    bs.DataSource = di;
            //    dataGridView2.AutoGenerateColumns = true;
            //    dataGridView2.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            //    dataGridView2.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells;
            //    dataGridView2.ReadOnly = true;
            //    dataGridView2.AllowUserToAddRows = false;
            //    dataGridView2.AllowUserToDeleteRows = false;
            //    dataGridView2.DataSource = bs;
            //    dataGridView2.Columns[4].Visible = false;
            //    dataGridView2.Columns[5].Visible = false;
            //    dataGridView2.Columns[6].Visible = false;
            //    dataGridView2.Columns[7].Visible = false;
            //    for (int i = 0; i < dataGridView2.Columns.Count - 1; i++)
            //    {
            //        dataGridView2.Columns[i].AutoSizeMode = DataGridViewAutoSizeColumnMode.AllCells;
            //    }
            //    throw new Exception();
            //}
            //catch (Exception)
            //{
            //    List<DisksLite> dl = new List<DisksLite>();
            //    DriveInfo[] di = DriveInfo.GetDrives();
            //    foreach (var item in di)
            //    {
            //        DisksLite dll = new DisksLite();
            //        dll.Disk = item.RootDirectory.Root.ToString();
            //        dl.Add(dll);
            //    }
            //    BindingSource bs = new BindingSource();
            //    bs.DataSource = dl;
            //    dataGridView2.AutoGenerateColumns = true;
            //    dataGridView2.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            //    dataGridView2.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells;
            //    dataGridView2.ReadOnly = true;
            //    dataGridView2.AllowUserToAddRows = false;
            //    dataGridView2.AllowUserToDeleteRows = false;
            //    dataGridView2.DataSource = bs;
               
            //}

            List<DisksLite> dl = new List<DisksLite>();
            DriveInfo[] di = DriveInfo.GetDrives();
            foreach (var item in di)
            {
                DisksLite dll = new DisksLite();
                dll.Disk = item.RootDirectory.Root.ToString();
                dl.Add(dll);
            }
            BindingSource bs = new BindingSource();
            bs.DataSource = dl;
            dataGridView2.AutoGenerateColumns = true;
            dataGridView2.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            dataGridView2.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells;
            dataGridView2.ReadOnly = true;
            dataGridView2.AllowUserToAddRows = false;
            dataGridView2.AllowUserToDeleteRows = false;
            dataGridView2.DataSource = bs;
            
            //foreach (var item in di)
            //{
            //    listBox2.Items.Add(item.RootDirectory +": "+ item.DriveType +" - " + item.DriveFormat + ": " + Math.Ceiling((double)(item.AvailableFreeSpace/1000/1000/1000)).ToString()+" free in "+Math.Ceiling((double)(item.TotalSize /1000/1000/1000)).ToString()+" Gb");
            //}
        }

        private long GetTotalFreeSpace(string driveName)
        {
            foreach (DriveInfo drive in DriveInfo.GetDrives())
            {
                if (drive.IsReady && drive.Name == driveName + ":\\")
                {
                    return drive.TotalFreeSpace;
                }
            }
            return -1;
        }

        private void InitDrives()
        {
            try
            {
                //var dicDrives = new Dictionary<int, HDD>();

                //var wdSearcher = new ManagementObjectSearcher("SELECT * FROM Win32_DiskDrive");

                //// extract model and interface information
                //int iDriveIndex = 0;
                //foreach (ManagementObject drive in wdSearcher.Get())
                //{
                //    var hdd = new HDD();
                //    hdd.Model = drive["Model"].ToString().Trim();
                //    hdd.Type = drive["InterfaceType"].ToString().Trim();
                //    dicDrives.Add(iDriveIndex, hdd);
                //    iDriveIndex++;
                //}

                //var pmsearcher = new ManagementObjectSearcher("SELECT * FROM Win32_PhysicalMedia");

                //// retrieve hdd serial number
                //iDriveIndex = 0;
                //foreach (ManagementObject drive in pmsearcher.Get())
                //{
                //    // because all physical media will be returned we need to exit
                //    // after the hard drives serial info is extracted
                //    if (iDriveIndex >= dicDrives.Count)
                //        break;

                //    dicDrives[iDriveIndex].Serial = drive["SerialNumber"] == null ? "None" : drive["SerialNumber"].ToString().Trim();
                //    iDriveIndex++;
                //}

                //// get wmi access to hdd 
                //var searcher = new ManagementObjectSearcher("Select * from Win32_DiskDrive");
                //searcher.Scope = new ManagementScope(@"\root\wmi");

                //// check if SMART reports the drive is failing
                //searcher.Query = new ObjectQuery("Select * from MSStorageDriver_FailurePredictStatus");
                //iDriveIndex = 0;
                //foreach (ManagementObject drive in searcher.Get())
                //{
                //    dicDrives[iDriveIndex].IsOK = (bool)drive.Properties["PredictFailure"].Value == false;
                //    iDriveIndex++;
                //}

                //// retrive attribute flags, value worste and vendor data information
                //searcher.Query = new ObjectQuery("Select * from MSStorageDriver_FailurePredictData");
                //iDriveIndex = 0;
                //foreach (ManagementObject data in searcher.Get())
                //{
                //    Byte[] bytes = (Byte[])data.Properties["VendorSpecific"].Value;
                //    for (int i = 0; i < 30; ++i)
                //    {
                //        try
                //        {
                //            int id = bytes[i * 12 + 2];

                //            int flags = bytes[i * 12 + 4]; // least significant status byte, +3 most significant byte, but not used so ignored.
                //            //bool advisory = (flags & 0x1) == 0x0;
                //            bool failureImminent = (flags & 0x1) == 0x1;
                //            //bool onlineDataCollection = (flags & 0x2) == 0x2;

                //            int value = bytes[i * 12 + 5];
                //            int worst = bytes[i * 12 + 6];
                //            int vendordata = BitConverter.ToInt32(bytes, i * 12 + 7);
                //            if (id == 0) continue;

                //            var attr = dicDrives[iDriveIndex].Attributes[id];
                //            attr.Current = value;
                //            attr.Worst = worst;
                //            attr.Data = vendordata;
                //            attr.IsOK = failureImminent == false;
                //        }
                //        catch
                //        {
                //            // given key does not exist in attribute collection (attribute not in the dictionary of attributes)
                //        }
                //    }
                //    iDriveIndex++;
                //}

                //// retreive threshold values foreach attribute
                //searcher.Query = new ObjectQuery("Select * from MSStorageDriver_FailurePredictThresholds");
                //iDriveIndex = 0;
                //foreach (ManagementObject data in searcher.Get())
                //{
                //    Byte[] bytes = (Byte[])data.Properties["VendorSpecific"].Value;
                //    for (int i = 0; i < 30; ++i)
                //    {
                //        try
                //        {

                //            int id = bytes[i * 12 + 2];
                //            int thresh = bytes[i * 12 + 3];
                //            if (id == 0) continue;

                //            var attr = dicDrives[iDriveIndex].Attributes[id];
                //            attr.Threshold = thresh;
                //        }
                //        catch
                //        {
                //            // given key does not exist in attribute collection (attribute not in the dictionary of attributes)
                //        }
                //    }

                //    iDriveIndex++;
                //}


                //foreach (var drive in dicDrives)
                //{
                //    if (drive.Value.Attributes.Count > 0)
                //    {
                //        HDDInfo hi = new HDDInfo();

                //        hi.Info = String.Format(" DRIVE ({0}): " + drive.Value.Serial + " - " + drive.Value.Model + " - " + drive.Value.Type, ((drive.Value.IsOK) ? "OK" : "BAD"));
                //        hi.Model = drive.Value.Model;
                //        hi.Serial = drive.Value.Serial;
                //        hi.Status = ((drive.Value.IsOK) ? "OK" : "BAD");
                //        hi.Type = drive.Value.Type;

                //        List<SmartAttr> atts = new List<SmartAttr>();
                //        foreach (var attr in drive.Value.Attributes)
                //        {
                //            if (attr.Value.HasData)
                //            {
                //                SmartAttr at = new SmartAttr();
                //                at.Attribute = attr.Value.Attribute;
                //                at.Current = attr.Value.Current;
                //                at.Data = attr.Value.Data;
                //                at.Worst = attr.Value.Worst;
                //                at.Threshold = attr.Value.Threshold;
                //                at.Status = ((attr.Value.IsOK) ? "OK" : "");
                //                atts.Add(at);
                //            }

                //        }
                //        hi.Attributes = atts;


                //        HarDrives.Add(hi);
                //        var n = listBox1.Items.Add(hi.Info);
                //        if (hi.Status == "OK")
                //        {
                //            listBox1.SelectedIndex = n;
                //        }
                //    }
                //}
            }
            catch (Exception)
            {
                
            }
            

        }

        List<HDDInfo> HarDrives = new List<HDDInfo>();

       public class HDDInfo
        {
            public List<SmartAttr> Attributes = new List<SmartAttr>();
            public string Serial { get; set; }
            public string Model { get; set; }
            public string Type { get; set; }
            public string Status { get; set; }
            public string Info { get; set; }
        }
       public class SmartAttr
        {
            public string Attribute { get; set; }
            public int Current { get; set; }
            public int Worst { get; set; }
            public int Threshold { get; set; }
            public int Data { get; set; }
            public string Status { get; set; }
        }

       private void listBox1_SelectedIndexChanged(object sender, EventArgs e)
       {
           BindingSource bs = new BindingSource();
           foreach (var drive in HarDrives )
           {
               if (drive.Info==listBox1.Text)
               {
                   bs.DataSource = drive.Attributes ;
                   dataGridView1.AutoGenerateColumns = true;
                   dataGridView1.DataSource = bs;
                   dataGridView1.Columns[0].AutoSizeMode = DataGridViewAutoSizeColumnMode.AllCells;
                   dataGridView1.AllowUserToAddRows = false;
               }
           }
           
       }

       string selectedDrive = "";
       private void dataGridView2_SelectionChanged(object sender, EventArgs e)
       {
           try
           {
               selectedDrive = (string)dataGridView2.SelectedRows[0].Cells[0].Value;
               label1.Text = "Selected: " + selectedDrive;
               button1.Enabled = true;
           }
           catch (Exception)
           {
               
           }
           
       }

       private void Form1_SizeChanged(object sender, EventArgs e)
       {
           
       }

       private void button1_Click_1(object sender, EventArgs e)
       {
           performanceCounter1.InstanceName = selectedDrive[0].ToString() + ":";
           performanceCounter1.NextSample();
           scanBox1.StartScan(selectedDrive,10000);
           button1.Visible = false;
           timer2.Enabled = true;
       }

       private void dataGridView2_CellContentClick(object sender, DataGridViewCellEventArgs e)
       {

       }

       private void timer2_Tick(object sender, EventArgs e)
       {
           label2.Text = Math.Ceiling((double)(performanceCounter1.NextValue()/1000/1000)).ToString()+" Mb\\s.";
       }

    }
}
